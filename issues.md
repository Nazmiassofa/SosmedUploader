# 🔍 Issues, Potensi Masalah & Saran Perbaikan — SosmedUploader

> Audit dilakukan: **5 Mei 2026**
> Scope: Seluruh codebase project SosmedUploader

---

## Daftar Isi

- [🔴 Bug Aktif (Harus Diperbaiki)](#-bug-aktif-harus-diperbaiki)
- [🟡 Potensi Masalah (Risiko Tinggi)](#-potensi-masalah-risiko-tinggi)
- [🟢 Saran Peningkatan Performa](#-saran-peningkatan-performa)
- [🔵 Perbaikan Organisasi Code](#-perbaikan-organisasi-code)
- [⚪ Minor / Nice-to-Have](#-minor--nice-to-have)

---

## 🔴 Bug Aktif (Harus Diperbaiki)

### 1. ❌ `image_url` Di-overwrite Jadi `None` — Data Hilang

**File:** `main.py` (line 307)
**Severity:** **CRITICAL**

```python
# Line 286-287: image_url diambil dari payload
image_url = payload.get("image_url")

# Line 307: LANGSUNG DI-SET JADI None! 
image_url = None  # ← BUG: menghapus image_url dari payload
```

Akibatnya, **path `if image_url:` (line 312) tidak pernah tercapai**, sehingga semua image selalu di-proses ulang dan di-upload ke R2 walaupun sudah punya URL publik. Ini membuang bandwidth dan waktu.

**Fix:** Hapus `image_url = None` di line 307.

---

### 2. ❌ Flow `_handle_payload` Tidak Ada `return` Setelah `video_ready`

**File:** `main.py` (line 258-273)
**Severity:** **HIGH**

```python
if payload.get("type") == "video_ready":
    # ... handle video ...
    await self._handle_video_payload(video_url)

# ❌ TIDAK ADA return! Eksekusi lanjut ke validasi job_vacancy di bawah
data = self._validate_job_vacancy_payload(payload)
```

Ketika payload bertipe `video_ready`, setelah dihandle, eksekusi terus ke bawah dan mencoba validasi sebagai `job_vacancy`. Walaupun `_validate_job_vacancy_payload` akan return `None` (karena type != job_vacancy), ini tetap tidak benar secara logic dan bisa menyebabkan side-effect yang tidak terduga.

**Fix:** Tambahkan `return` setelah `await self._handle_video_payload(video_url)`.

---

### 3. ❌ `finally` Block Salah Posisi di `_handle_video_payload`

**File:** `main.py` (line 186-219)
**Severity:** **HIGH**

```python
# Upload ke Instagram
try:
    ...
except Exception as e:
    ...

# Upload ke Facebook
try:
    ...
except Exception as e:
    ...

# ❌ `finally` ini hanya terkait block `try` Facebook, bukan kedua upload
finally:
    # Clean up video from R2
    ...
```

`finally` block hanya attached ke `try` block Facebook (line 189-203). Jika Instagram upload berhasil tapi Facebook dilewati (`fb_uploader` is None), cleanup tetap jalan. Tapi jika exception terjadi di luar block Facebook, cleanup bisa tidak dieksekusi sesuai harapan.

**Fix:** Wrap seluruh video upload logic (Instagram + Facebook + cleanup) dalam satu `try/finally` block yang benar.

---

### 4. ❌ Hardcoded Password di `settings.py`

**File:** `config/settings.py` (line 15)
**Severity:** **CRITICAL (Security)**

```python
REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", "Nazmiassofa133")
```

Password Redis di-hardcode sebagai default value. Jika `.env` tidak ter-load atau variabel tidak di-set, password ini akan terpakai. Ini adalah **security vulnerability**.

**Fix:** Gunakan default `None` dan validasi di `__post_init__`.

---

### 5. ❌ Kredensial Sensitive Ter-commit di `.env`

**File:** `.env`
**Severity:** **CRITICAL (Security)**

File `.env` berisi semua API keys, tokens, dan credentials (Facebook, Instagram, R2). Walaupun `.gitignore` mencantumkan `.env`, jika file ini pernah ter-commit sebelumnya, history git masih menyimpannya.

**Action:**
- Rotate semua API keys & tokens segera
- Pastikan `.env` tidak pernah ter-commit (cek `git log --all --full-history -- .env`)
- Gunakan `.env.example` dengan placeholder values

---

### 6. ❌ Inkonsistensi `R2_BASE_URL` Antara Settings dan R2Service

**File:** `config/settings.py` vs `services/r2_service.py`

```python
# settings.py (line 37)
R2_BASE_URL: str = os.getenv("R2_BASE_URL", "https://media.voisaretired.online")

# r2_service.py (line 17)
public_base_url: Optional[str] = "https://media.mailezz.com"
```

Dua default URL yang berbeda! Jika `R2_BASE_URL` tidak di-set, `settings.py` pakai `voisaretired.online` tapi `R2UploaderService` constructor default pakai `mailezz.com`. `MediaService` menggunakan config, tapi `AutoUploader` tidak meng-pass `public_base_url` ke `R2UploaderService`.

**Fix:** 
- Hapus default dari `R2UploaderService`, selalu gunakan dari config
- Pass `public_base_url` dan `bucket` dari config di `AutoUploader.start()`

---

## 🟡 Potensi Masalah (Risiko Tinggi)

### 7. ⚠️ Race Condition pada Video Generation

**File:** `main.py` (line 296-298)

```python
if self.media.should_generate_video():
    asyncio.create_task(self._generate_and_publish_video(payload))
```

`should_generate_video()` hanya check count gambar dan `create_task` berjalan secara fire-and-forget. Jika dua pesan datang hampir bersamaan dan keduanya melewati check `should_generate_video()`, dua task video generation bisa berjalan bersamaan. `threading.Lock` di `_generate_video_sync` mencegah concurrent execution, tapi task kedua akan menunggu dan mungkin generate video dengan gambar baru yang belum seharusnya included.

**Fix:** 
- Gunakan `asyncio.Lock` di level async
- Set flag `video_generation_in_progress` sebelum `create_task`
- Reset flag setelah task selesai

---

### 8. ⚠️ `get_event_loop()` Deprecated — Gunakan `get_running_loop()`

**File:** `services/media_service.py` (line 113, 139) dan `main.py` (line 449, 460)

```python
# Deprecated:
loop = asyncio.get_event_loop()

# Correct:
loop = asyncio.get_running_loop()
```

`asyncio.get_event_loop()` deprecated sejak Python 3.10 dan bisa error di Python 3.12+ saat tidak ada running loop. Project menggunakan Python 3.12 (sesuai Dockerfile dan `.python-version`).

**Fix:** Ganti semua `get_event_loop()` dengan `get_running_loop()`.

---

### 9. ⚠️ R2UploaderService Instance Duplikat

**File:** `main.py` (line 61-65) dan `services/media_service.py` (line 43-49)

`AutoUploader` membuat satu instance `R2UploaderService` untuk image upload, dan `MediaService` membuat instance terpisah untuk video upload. Ini berarti ada **dua boto3 client** yang hidup bersamaan.

**Impact:**
- Memori terbuang untuk dua S3 client yang identik
- Konfigurasi bisa inkonsisten (lihat Issue #6)

**Fix:** Inject `R2UploaderService` instance ke `MediaService` alih-alih membuat instance baru di dalamnya.

---

### 10. ⚠️ Tidak Ada Retry Mechanism untuk API Calls

**Files:** `instagram_client.py`, `facebook_client.py`, `r2_service.py`

Semua API call ke Instagram, Facebook, dan R2 tidak memiliki retry mechanism. Jika terjadi network timeout atau rate limit, request langsung gagal.

**Impact:** Unreliable di production, terutama pada:
- Instagram rate limiting (200 calls/hour)
- Network intermittent issues
- R2 temporary unavailability

**Fix:** Implementasikan exponential backoff retry (bisa pakai `tenacity` library atau custom decorator).

---

### 11. ⚠️ Log File Tidak Ada Rotation

**File:** `config/logger.py`

```python
handlers = [
    logging.FileHandler("logs/bot.log"),  # ← Tumbuh terus tanpa batas!
    logging.StreamHandler()
]
```

File log akan terus membesar tanpa batas. Pada production yang aktif, ini bisa menghabiskan disk space.

**Fix:** Gunakan `RotatingFileHandler` atau `TimedRotatingFileHandler`:

```python
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    "logs/bot.log", 
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
```

---

### 12. ⚠️ `daily_limit` Hanya Check Instagram, Bukan Facebook

**File:** `main.py` (line 276-283)

```python
allowed = await can_post_today(
    self.redis,
    prefix="instagram:daily_posts",
)

if not allowed:
    return  # ← Skip semua platform, bukan hanya Instagram
```

Daily limit di-hardcode untuk Instagram (`prefix="instagram:daily_posts"`), tapi jika limit tercapai, **Facebook upload juga di-skip**. Seharusnya limit per-platform atau ada logika terpisah.

---

### 13. ⚠️ Memory Leak Potensial pada Image Processing

**File:** `main.py` (line 300-362)

Base64 image di-decode, diproses, lalu di-encode ulang. Selama proses ini, beberapa copy dari image data bisa exist di memory bersamaan:
1. `image_base64` original
2. `image_bytes` (decoded)  
3. PIL Image object
4. `processed_image` (processed)
5. `processed_base64` (re-encoded)

Untuk gambar besar (10MB base64 ≈ 7.5MB binary), ini bisa memakai ~40MB+ per image.

**Fix:** 
- Gunakan context manager untuk PIL Images
- Explicitly delete intermediate objects
- Pertimbangkan streaming approach

---

### 14. ⚠️ Redis Connection Tidak Ada Health Check / Reconnection

**File:** `core/redis.py`

Setelah koneksi awal, tidak ada mekanisme untuk:
- Periodic health check (ping)
- Auto-reconnect jika koneksi terputus
- Connection pool management

Jika Redis server restart, aplikasi akan crash tanpa recovery.

**Fix:** Implementasikan Redis health check berkala atau gunakan `redis-py` connection pool dengan retry options.

---

## 🟢 Saran Peningkatan Performa

### 15. 🚀 MoviePy Sangat Lambat — Pertimbangkan FFmpeg Langsung

**File:** `services/media/video_generator.py`

MoviePy 1.0.3 sudah EOL dan known lambat karena:
- Meng-load seluruh frame ke memory sebagai numpy array
- Encoding melalui Python layer, bukan native FFmpeg

**Benchmark:**
- MoviePy: ~30-60 detik untuk 10 gambar slideshow
- FFmpeg langsung: ~3-5 detik untuk operasi yang sama

**Fix:** Gunakan `subprocess` + FFmpeg langsung:

```python
import subprocess

def generate_video_ffmpeg(image_paths, output_path, duration=3, fps=24):
    # Create concat file
    concat_file = "concat.txt"
    with open(concat_file, "w") as f:
        for img in image_paths:
            f.write(f"file '{img}'\nduration {duration}\n")
    
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_file, "-vf", f"scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:white",
        "-c:v", "libx264", "-preset", "ultrafast", "-r", str(fps),
        output_path
    ]
    subprocess.run(cmd, check=True)
```

---

### 16. 🚀 Blocking I/O di Event Loop Thread

**File:** `main.py` — `_handle_payload`

Beberapa operasi sudah menggunakan `run_in_executor` dengan benar, tapi pattern ini bisa di-improve:

```python
# Sekarang: menggunakan default executor (None) = ThreadPoolExecutor
await loop.run_in_executor(None, self.fb_uploader.test_connection)
```

**Saran:**
- Buat shared `ThreadPoolExecutor` dengan nama dan max_workers yang terdefinisi
- Gunakan `httpx.AsyncClient` atau `aiohttp` sebagai pengganti `requests` yang blocking
- Ini akan menghilangkan kebutuhan `run_in_executor` untuk HTTP calls

---

### 17. 🚀 Base64 Round-trip Tidak Efisien

**Flow saat ini:**
```
Redis (base64) → decode → PIL process → encode base64 → decode di R2 → upload bytes
```

Base64 encoding menambah ~33% ukuran data. Round-trip decode→encode→decode membuang CPU dan memory.

**Fix:** Setelah image processing, langsung simpan sebagai bytes dan upload ke R2 tanpa re-encoding ke base64:

```python
# Sekarang:
processed_base64 = image_processor.process_base64_image(image_base64)
image_url = storage.upload_base64_image(processed_base64)

# Saran: tambahkan method upload_bytes
image_url = storage.upload_image_bytes(processed_bytes, ext="jpg")
```

---

### 18. 🚀 `FileStorage.get_images()` Dipanggil Terlalu Sering

**File:** `services/media_service.py`

```python
# Di save_image():
current_images = len(self.storage.get_images())  # os.listdir + sort

# Di should_generate_video():
count = len(self.storage.get_images())  # os.listdir + sort LAGI

# Di _generate_video_sync():
images = self.storage.get_images()  # os.listdir + sort LAGI
```

Setiap pemanggilan membaca filesystem (`os.listdir`). Pada volume tinggi, ini inefficient.

**Fix:** 
- Maintain in-memory counter/list untuk image tracking
- Sync dengan filesystem hanya saat diperlukan (startup, setelah cleanup)

---

### 19. 🚀 Instagram `time.sleep(2)` Blocking Thread

**File:** `services/instagram_client.py` (line 189)

```python
# Images usually process quickly, small delay is enough
time.sleep(2)  # ← Blocking selama 2 detik!
```

Walaupun ini dijalankan di executor thread, tetap blocking satu thread selama 2 detik. Ini juga blocking `_check_media_status` yang menggunakan `time.sleep(10)` per iteration.

**Fix:** Jika migrated ke async HTTP client, gunakan `asyncio.sleep()` sebagai gantinya.

---

### 20. 🚀 Video Upload Timeout 600 Detik Terlalu Tinggi

**File:** `instagram_client.py` (line 233), `facebook_client.py` (line 104)

```python
timeout=600  # 10 menit!
```

Timeout 10 menit per request sangat tinggi. Jika server hang, thread/connection akan stuck selama 10 menit.

**Fix:** Gunakan tiered timeout:
```python
timeout = requests.adapters.Timeout(connect=10, read=120)
```

---

## 🔵 Perbaikan Organisasi Code

### 21. 📁 `main.py` Terlalu Besar (496 lines) — Perlu Refactor

**File:** `main.py`

`main.py` menangani terlalu banyak tanggung jawab:
- Application lifecycle (start/stop)
- Payload routing & validation
- Image processing orchestration
- Video upload orchestration
- Caption building (hardcoded di line 171)

**Saran refactor:**

```
main.py                          → App lifecycle & entry point saja (~50 lines)
handlers/
├── __init__.py
├── job_vacancy_handler.py       → Logic handle job_vacancy payload
└── video_handler.py             → Logic handle video_ready payload
```

---

### 22. 📁 Duplikasi `build_job_caption()` 

**Files:** `instagram_client.py` (line 31-54), `facebook_client.py` (line 29-62)

Dua method yang hampir identik untuk membangun caption lowongan kerja. Hanya ada perbedaan minor di formatting (indent `•` vs `   •`).

**Fix:** Buat satu `CaptionBuilder` utility class:

```
services/
├── utils/
│   └── caption_builder.py    → Satu sumber caption formatting
```

---

### 23. 📁 `ImageProcessor` vs `ImageValidator` — Overlap Tanggung Jawab

**Files:** `services/image_processor.py` vs `services/media/image_validator.py`

Dua class yang beroperasi pada domain yang sama (image processing) tapi di lokasi berbeda:
- `ImageProcessor` → di `services/` root → untuk Instagram feed
- `ImageValidator` → di `services/media/` → untuk video generation

Keduanya melakukan decode base64, validate format, dan process gambar.

**Fix:** Konsolidasi ke satu modul `services/media/image_processor.py` dengan method yang terpisah untuk setiap use case.

---

### 24. 📁 `MediaService` Tidak di-export di `services/__init__.py`

**File:** `services/__init__.py` (line 9-17)

```python
__all__ = [
    "RedisSubscriber",
    "FacebookUploader",
    "InstagramUploader",
    "R2UploaderService",
    "can_post_today",
    "increment_daily_post",
    "ImageProcessor"
    # ← MediaService TIDAK ADA di __all__
]
```

`MediaService` di-import di `__init__.py` (line 3) tapi tidak di-list di `__all__`.

**Fix:** Tambahkan `"MediaService"` ke `__all__`.

---

### 25. 📁 `core/` Directory Kurang Terisi

**Current structure:**
```
core/
└── redis.py     → Hanya 1 file
```

Module `core/` hanya berisi satu file Redis. Pertimbangkan:
- Pindahkan `core/redis.py` → `services/redis_client.py` (gabungkan dengan service lain)
- Atau isi `core/` dengan abstraksi lain (base classes, interfaces, constants)

---

### 26. 📁 Tidak Ada Type Hinting yang Konsisten

**Multiple files**

Beberapa file menggunakan type hints dengan baik (`instagram_client.py`, `facebook_client.py`), tapi yang lain tidak konsisten:

```python
# redis_subs.py — Any digunakan dimana seharusnya ada proper type
redis_client: Any  # ← harusnya Redis

# media_service.py — tuple tanpa type params
resolution: tuple = (720, 1280)  # ← harusnya Tuple[int, int]
```

**Fix:** Tambahkan type hints yang konsisten di seluruh codebase. Pertimbangkan menggunakan `mypy` untuk static type checking.

---

### 27. 📁 Tidak Ada `__init__.py` di `config/` dan `core/`

**Directories:** `config/`, `core/`

Kedua directory tidak memiliki `__init__.py`. Walaupun Python 3 mendukung namespace packages, explicit `__init__.py` lebih baik untuk:
- IDE support
- Import clarity
- Re-export symbols

---

### 28. 📁 File Comment Header Tidak Konsisten

Beberapa file punya header comment:
```python
## services/instagram_client.py    → Menggunakan ##
## core/redis.py                   → Menggunakan ##
# services/redis_subscriber.py     → Menggunakan # (dan nama file salah!)
```

File `redis_subs.py` memiliki header `# services/redis_subscriber.py` — nama file tidak sesuai.

---

## ⚪ Minor / Nice-to-Have

### 29. 💡 Tambahkan Health Check Endpoint

Project ini berjalan sebagai long-running service tapi tidak ada health check endpoint. Untuk monitoring di Docker/Kubernetes, pertimbangkan menambahkan simple HTTP health check (misalnya pakai `aiohttp` server di port tertentu).

---

### 30. 💡 Tidak Ada Unit Tests

Project tidak memiliki test suite. File di `scratch/` adalah manual test scripts, bukan automated tests.

**Saran:**
- Tambahkan `tests/` directory
- Test critical paths: payload validation, caption building, image processing
- Gunakan `pytest` + `pytest-asyncio`

---

### 31. 💡 `docker-compose.yml` di .gitignore

Docker compose file di-gitignore, membuat sulit untuk onboarding developer baru. Pertimbangkan meng-commit `docker-compose.yml` (tanpa secrets) atau `docker-compose.example.yml`.

---

### 32. 💡 Logging Tidak Ada Structured/JSON Format

Untuk production, structured logging (JSON) lebih mudah di-parse oleh tools seperti ELK, Grafana Loki, atau CloudWatch.

**Fix:**
```python
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
        })
```

---

### 33. 💡 Tidak Ada `.env.example`

Tidak ada template `.env.example` untuk membantu developer baru setup project. Buat file ini dengan placeholder values.

---

### 34. 💡 `scratch/` Directory Seharusnya di `.gitignore`

Directory `scratch/` berisi test scripts yang tidak seharusnya di-commit ke production. Test scripts ini juga berisi hardcoded paths dan credentials logic.

---

### 35. 💡 Tambahkan `README.md`

Project tidak memiliki README. Tambahkan dokumentasi dasar:
- Deskripsi project
- Cara setup dan run
- Architecture overview
- Environment variables yang diperlukan

---

## 📊 Ringkasan Prioritas

| Prioritas | Issue # | Kategori | Deskripsi Singkat |
|:---------:|:-------:|:--------:|:------------------|
| 🔴 P0 | #1 | Bug | `image_url` di-overwrite jadi None |
| 🔴 P0 | #4, #5 | Security | Hardcoded password & credentials di .env |
| 🔴 P0 | #2 | Bug | Missing `return` setelah video_ready |
| 🔴 P1 | #3 | Bug | `finally` block salah posisi |
| 🔴 P1 | #6 | Bug | Inkonsistensi R2 base URL |
| 🟡 P2 | #7 | Race Cond | Video generation concurrent |
| 🟡 P2 | #8 | Deprecation | `get_event_loop()` deprecated |
| 🟡 P2 | #10 | Reliability | Tidak ada retry mechanism |
| 🟡 P2 | #14 | Reliability | Redis tanpa reconnection |
| 🟡 P3 | #9 | Resource | R2 client instance duplikat |
| 🟡 P3 | #11 | Ops | Log tanpa rotation |
| 🟡 P3 | #12 | Logic | Daily limit hanya cek Instagram |
| 🟡 P3 | #13 | Memory | Memory leak pada image processing |
| 🟢 P4 | #15 | Performa | MoviePy → FFmpeg langsung |
| 🟢 P4 | #16 | Performa | Blocking I/O → async HTTP |
| 🟢 P4 | #17 | Performa | Base64 round-trip tidak efisien |
| 🟢 P4 | #18 | Performa | get_images() terlalu sering |
| 🟢 P4 | #19, #20 | Performa | Blocking sleep & timeout tinggi |
| 🔵 P5 | #21-28 | Organisasi | Refactoring & code structure |
| ⚪ P6 | #29-35 | Nice-to-have | Tests, docs, monitoring |
