"""
File storage management service
"""
import os
import time
import uuid
import logging
import aiofiles
from typing import List, Union

log = logging.getLogger(__name__)

class FileStorage:
    """Handles file system operations for images and videos"""
    
    def __init__(self, image_dir: str = "data/images", video_dir: str = "data/videos"):
        self.image_dir = image_dir
        self.video_dir = video_dir
        
        # Create directories if they don't exist
        os.makedirs(self.image_dir, exist_ok=True)
        os.makedirs(self.video_dir, exist_ok=True)
    
    async def save_image(self, image_bytes: bytes) -> str:
        """
        Save image bytes to disk
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            str: Full path to saved image
        """
        filename = f"{int(time.time())}_{uuid.uuid4().hex}.jpg"
        file_path = os.path.join(self.image_dir, filename)
        
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(image_bytes)
        
        log.debug(f"[ STORAGE ] Image saved: {file_path}")
        return file_path
    
    def get_images(self) -> List[str]:
        """
        Get sorted list of image paths
        
        Returns:
            List[str]: Sorted list of full paths to images
        """
        files = [
            os.path.join(self.image_dir, f)
            for f in os.listdir(self.image_dir)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]
        files.sort()
        return files
    
    def get_video_path(self) -> str:
        """
        Generate unique video file path
        
        Returns:
            str: Full path for new video file
        """
        filename = f"slideshow_{int(time.time())}_{uuid.uuid4().hex}.mp4"
        return os.path.join(self.video_dir, filename)
    
    def cleanup_images(self, images: List[str]) -> None:
        """
        Remove image files from disk
        
        Args:
            images: List of image paths to remove
        """
        for img_path in images:
            try:
                if os.path.exists(img_path):
                    os.remove(img_path)
                    log.debug(f"[ STORAGE ] Image removed: {img_path}")
            except Exception as e:
                log.warning(f"[ STORAGE ] Failed to remove {img_path}: {e}")
    
    def cleanup_videos(self, videos: Union[List[str], str]) -> None:
        """
        Remove video file(s) from disk
        
        Args:
            videos: Single video path or list of video paths
        """
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
