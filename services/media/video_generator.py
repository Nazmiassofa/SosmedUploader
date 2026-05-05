## services/media/video_generator.py
"""
Video generation service using FFmpeg subprocess — fast and memory-efficient.
"""

import logging
import os
import random
import subprocess
import tempfile
from typing import List, Optional, Tuple

from PIL import Image, ImageOps

log = logging.getLogger(__name__)

SOUNDTRACK_DIR = "data/templates/sound"


class VideoGenerator:
    """Generates slideshow videos from images using FFmpeg directly."""

    def __init__(
        self,
        resolution: Tuple[int, int] = (720, 1280),
        duration_per_image: float = 3.0,
        fps: int = 24,
        background_color: Tuple[int, int, int] = (255, 255, 255),
    ):
        self.resolution = resolution  # (width, height)
        self.duration_per_image = duration_per_image
        self.fps = fps
        self.background_color = background_color

    def _pick_random_audio(self) -> Optional[str]:
        """Pick one random audio file from SOUNDTRACK_DIR"""
        if not os.path.isdir(SOUNDTRACK_DIR):
            log.warning(f"[ VIDEO ] Sound directory not found: {SOUNDTRACK_DIR}")
            return None

        audio_exts = (".mp3", ".wav", ".aac", ".m4a", ".ogg")
        audio_files = [
            os.path.join(SOUNDTRACK_DIR, f)
            for f in os.listdir(SOUNDTRACK_DIR)
            if f.lower().endswith(audio_exts)
        ]

        if not audio_files:
            log.warning("[ VIDEO ] No audio files found in sound directory")
            return None

        return audio_files[0] if len(audio_files) == 1 else random.choice(audio_files)

    def _prepare_image(self, img_path: str, output_path: str) -> bool:
        """
        Pre-process a single image: fix orientation, fit within resolution,
        center on background. Saves as PNG for lossless FFmpeg input.
        """
        try:
            with Image.open(img_path) as img:
                # Fix EXIF orientation
                img = ImageOps.exif_transpose(img)

                if img.mode != "RGB":
                    img = img.convert("RGB")

                target_w, target_h = self.resolution
                orig_w, orig_h = img.size

                # Scale to fit within target resolution (maintain aspect ratio)
                scale = min(target_w / orig_w, target_h / orig_h)
                new_w = int(orig_w * scale)
                new_h = int(orig_h * scale)

                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                # Center on background
                bg = Image.new("RGB", (target_w, target_h), self.background_color)
                paste_x = (target_w - new_w) // 2
                paste_y = (target_h - new_h) // 2
                bg.paste(img, (paste_x, paste_y))

                bg.save(output_path, format="PNG")

            return True
        except Exception as e:
            log.error(f"[ VIDEO ] Failed to prepare image {img_path}: {e}")
            return False

    def generate(self, image_paths: List[str], output_path: str) -> bool:
        """
        Generate slideshow video from images using FFmpeg.

        Args:
            image_paths: List of paths to image files
            output_path: Path where video should be saved

        Returns:
            True if successful, False otherwise
        """
        if not image_paths:
            log.error("[ VIDEO ] No image paths provided")
            return False

        # Verify ffmpeg is available
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True, check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            log.error("[ VIDEO ] FFmpeg not found. Install ffmpeg first.")
            return False

        temp_dir = None
        try:
            # Create temp directory for processed images
            temp_dir = tempfile.mkdtemp(prefix="video_gen_")

            # Pre-process all images (EXIF fix, resize, center)
            prepared_paths: List[str] = []
            for i, img_path in enumerate(image_paths):
                prepared_path = os.path.join(temp_dir, f"frame_{i:04d}.png")
                if self._prepare_image(img_path, prepared_path):
                    prepared_paths.append(prepared_path)
                else:
                    log.warning(f"[ VIDEO ] Skipping {img_path}")

            if not prepared_paths:
                log.error("[ VIDEO ] No images could be prepared")
                return False

            # Create FFmpeg concat demuxer file
            concat_file = os.path.join(temp_dir, "concat.txt")
            with open(concat_file, "w") as f:
                for path in prepared_paths:
                    # Escape single quotes in path
                    safe_path = path.replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")
                    f.write(f"duration {self.duration_per_image}\n")
                # Repeat last frame to avoid black frame at end
                safe_last = prepared_paths[-1].replace("'", "'\\''")
                f.write(f"file '{safe_last}'\n")

            # Build FFmpeg command
            width, height = self.resolution
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
            ]

            # Add audio if available
            audio_path = self._pick_random_audio()
            if audio_path:
                cmd.extend(["-i", audio_path])

            # Video encoding settings
            cmd.extend([
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=disable",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                "-r", str(self.fps),
            ])

            # Audio settings
            if audio_path:
                total_duration = len(prepared_paths) * self.duration_per_image
                cmd.extend([
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-shortest",
                    "-t", str(total_duration),
                ])
            else:
                cmd.extend(["-an"])

            cmd.append(output_path)

            log.info(f"[ VIDEO ] Generating video with {len(prepared_paths)} images...")
            log.debug(f"[ VIDEO ] FFmpeg command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                log.error(f"[ VIDEO ] FFmpeg failed:\n{result.stderr[-500:]}")
                return False

            log.info(f"[ VIDEO ] Video generated: {output_path}")
            return True

        except subprocess.TimeoutExpired:
            log.error("[ VIDEO ] FFmpeg timed out after 300 seconds")
            return False
        except Exception as e:
            log.error(f"[ VIDEO ] Failed to generate video: {e}", exc_info=True)
            return False
        finally:
            # Clean up temp directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    for f in os.listdir(temp_dir):
                        os.remove(os.path.join(temp_dir, f))
                    os.rmdir(temp_dir)
                except Exception as e:
                    log.warning(f"[ VIDEO ] Temp cleanup failed: {e}")
