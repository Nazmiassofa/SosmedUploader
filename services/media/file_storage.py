## services/media/file_storage.py
"""
File storage management service with in-memory tracking.
"""

import os
import time
import uuid
import logging
import asyncio
import aiofiles
from typing import List, Union

log = logging.getLogger(__name__)


class FileStorage:
    """Handles file system operations for images and videos with cached tracking."""

    def __init__(self, image_dir: str = "data/images", video_dir: str = "data/videos"):
        self.image_dir = image_dir
        self.video_dir = video_dir

        os.makedirs(self.image_dir, exist_ok=True)
        os.makedirs(self.video_dir, exist_ok=True)

        # In-memory image list — avoids repeated os.listdir calls
        self._image_paths: List[str] = self._scan_images()
        self._lock = asyncio.Lock()

    def _scan_images(self) -> List[str]:
        """Scan filesystem for images (used at startup and after cleanup)"""
        files = [
            os.path.join(self.image_dir, f)
            for f in os.listdir(self.image_dir)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]
        files.sort()
        return files

    async def save_image(self, image_bytes: bytes) -> str:
        """
        Save image bytes to disk and update in-memory list.
        
        Returns:
            str: Full path to saved image
        """
        filename = f"{int(time.time())}_{uuid.uuid4().hex}.jpg"
        file_path = os.path.join(self.image_dir, filename)

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(image_bytes)

        async with self._lock:
            self._image_paths.append(file_path)
            self._image_paths.sort()

        log.debug(f"[ STORAGE ] Image saved: {file_path}")
        return file_path

    def get_images(self) -> List[str]:
        """Get sorted list of tracked image paths (from memory, no disk I/O)"""
        return list(self._image_paths)

    def get_image_count(self) -> int:
        """Get count of tracked images without copying the list"""
        return len(self._image_paths)

    def get_video_path(self) -> str:
        """Generate unique video file path"""
        filename = f"slideshow_{int(time.time())}_{uuid.uuid4().hex}.mp4"
        return os.path.join(self.video_dir, filename)

    def cleanup_images(self, images: List[str]) -> None:
        """Remove image files from disk and update in-memory list"""
        removed = set()
        for img_path in images:
            try:
                if os.path.exists(img_path):
                    os.remove(img_path)
                    removed.add(img_path)
                    log.debug(f"[ STORAGE ] Image removed: {img_path}")
            except Exception as e:
                log.warning(f"[ STORAGE ] Failed to remove {img_path}: {e}")

        # Update in-memory list
        if removed:
            self._image_paths = [p for p in self._image_paths if p not in removed]

    def cleanup_videos(self, videos: Union[List[str], str]) -> None:
        """Remove video file(s) from disk"""
        if not videos:
            return

        if isinstance(videos, str):
            videos = [videos]

        for video_path in videos:
            try:
                if os.path.exists(video_path):
                    os.remove(video_path)
                    log.info(f"[ STORAGE ] Video removed: {video_path}")
            except Exception as e:
                log.warning(f"[ STORAGE ] Failed to remove video {video_path}: {e}")
