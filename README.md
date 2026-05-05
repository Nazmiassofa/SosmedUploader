# SosmedUploader

Auto-uploader bot untuk posting lowongan kerja ke Instagram dan Facebook, dikendalikan via Redis pub/sub.

## Fitur

- 📸 Upload gambar lowongan kerja ke **Instagram Feed** dan **Facebook Page**
- 🎬 Generate video slideshow otomatis dari gambar yang terkumpul → upload ke **Instagram Reels** dan **Facebook Video**
- 🔄 Proses gambar otomatis (aspect ratio, EXIF orientation) untuk compliance Instagram
- 📊 Rate limiting per-platform (Instagram dan Facebook terpisah)
- ☁️ Storage gambar via **Cloudflare R2**
- 🔁 Redis pub/sub untuk menerima payload dari service lain

## Architecture

```
Redis PubSub → AutoUploader (main.py)
                    ├── JobVacancyHandler → Instagram + Facebook (image)
                    ├── VideoHandler → Instagram Reels + Facebook (video)
                    └── MediaService → VideoGenerator (FFmpeg) → R2 Upload
```

## Setup

### Prerequisites

- Python 3.12+
- Redis server
- FFmpeg (`apt install ffmpeg`)
- Cloudflare R2 bucket

### Installation

```bash
# Clone & install
git clone <repo-url>
cd SosmedUploader
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your credentials

# Run
python main.py
```

### Docker

```bash
cp docker-compose.example.yml docker-compose.yml
cp .env.example .env
# Edit .env & docker-compose.yml

docker compose up -d
```

## Environment Variables

Lihat [`.env.example`](.env.example) untuk daftar lengkap.

| Variable | Required | Description |
|:---------|:--------:|:------------|
| `PAGE_ACCESS_TOKEN` | ✅ | Meta Graph API page access token |
| `INSTAGRAM_ID` | ✅ | Instagram Business Account ID |
| `FACEBOOK_PAGE_ID` | ✅ | Facebook Page ID |
| `REDIS_HOST` | ✅ | Redis server host |
| `REDIS_PASSWORD` | ✅ | Redis password |
| `R2_ACCOUNT_ID` | ✅ | Cloudflare R2 account ID |
| `R2_ACCESS_KEY` | ✅ | R2 access key |
| `R2_SECRET_KEY` | ✅ | R2 secret key |
| `ENVIRONMENT` | ❌ | `DEV` or `PROD` (default: `DEV`) |

## Project Structure

```
├── main.py                  # Entry point & AutoUploader lifecycle
├── config/
│   ├── settings.py          # Environment configuration
│   └── logger.py            # Logging setup (rotating + JSON)
├── core/
│   └── redis.py             # Redis connection with health check
├── handlers/
│   ├── job_vacancy_handler.py  # Image post processing
│   └── video_handler.py        # Video upload handling
├── services/
│   ├── instagram_client.py  # Instagram Graph API (async httpx)
│   ├── facebook_client.py   # Facebook Graph API (async httpx)
│   ├── r2_service.py        # Cloudflare R2 storage
│   ├── media_service.py     # Media orchestrator
│   ├── redis_subs.py        # Redis subscriber
│   ├── redis_limits.py      # Rate limiting
│   ├── utils/
│   │   ├── caption_builder.py  # Shared caption formatting
│   │   └── retry.py            # Async retry decorator
│   └── media/
│       ├── image_processor.py  # Image validation & processing
│       ├── video_generator.py  # FFmpeg video generation
│       └── file_storage.py     # Local file management
├── Dockerfile
├── requirements.txt
└── .env.example
```
