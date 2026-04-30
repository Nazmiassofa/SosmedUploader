"""
Main media service orchestrator
"""
import logging
import asyncio
import threading
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor

from config.settings import config
from services.media import FileStorage, ImageValidator, VideoGenerator
from services.r2_service import R2UploaderService

log = logging.getLogger(__name__)

class MediaService:
    """
    Orchestrates media processing workflow:
    - Image validation and storage
    - Video generation
    - Cloud upload
    """
    
    def __init__(
        self,
        image_dir: str = "data/images",
        video_dir: str = "data/videos",
        min_images: int = 10,
        resolution: tuple = (720, 1280),
        duration_per_image: float = 3.0,
        fps: int = 24,
    ):
        self.min_images = min_images
        
        # Initialize sub-services
        self.validator = ImageValidator()
        self.storage = FileStorage(image_dir, video_dir)
        self.video_gen = VideoGenerator(
            resolution=resolution,
            duration_per_image=duration_per_image,
            fps=fps
        )
        self.uploader = R2UploaderService(
            account_id=config.R2_ACCOUNT_ID,
            access_key=config.R2_ACCESS_KEY,
            secret_key=config.R2_SECRET_KEY,
            public_base_url=config.R2_BASE_URL,
            bucket=config.R2_BUCKET
        )
        
        # Thread management
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.video_generation_lock = threading.Lock()
        
        self.max_images = 100
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.executor:
            self.executor.shutdown(wait=True)
            log.info("[ MEDIA ] ThreadPoolExecutor shut down")
    
    async def save_image(self, image_base64: str) -> bool:
        """
        Validate and save base64 image to disk with limit protection
        """
        image_bytes = None
        try:
            # Check limit BEFORE validation
            current_images = len(self.storage.get_images())
            if current_images >= self.max_images:
                log.warning(f"[ MEDIA ] Max images reached: {current_images}/{self.max_images}")
                images = self.storage.get_images()
                excess = current_images - self.min_images
                if excess > 0:
                    to_remove = images[:excess]
                    self.storage.cleanup_images(to_remove)
                    log.info(f"[ MEDIA ] Cleaned up {len(to_remove)} old images")

            image_bytes = self.validator.validate(image_base64)
            if not image_bytes:
                return False

            await self.storage.save_image(image_bytes)
            return True

        except Exception as e:
            log.error(f"[ MEDIA ] Failed to save image: {e}")
            return False
        finally:
            if image_bytes is not None:
                del image_bytes

    def should_generate_video(self) -> bool:
        """
        Check if there are enough images to generate a video
        """
        count = len(self.storage.get_images())
        log.debug(f"[ MEDIA ] Image count: {count}/{self.min_images}")
        return count >= self.min_images
    
    async def generate_and_upload_video(self) -> Optional[str]:
        """
        Generate video from images and upload to cloud storage
        """
        # Generate video file
        video_path = await self._generate_video_async()
        if not video_path:
            return None
        
        try:
            # Upload to cloud storage
            loop = asyncio.get_event_loop()
            video_url = await loop.run_in_executor(
                self.executor,
                self.uploader.upload_video,
                video_path
            )
            
            if not video_url:
                log.error("[ MEDIA ] Upload failed: no URL returned")
                return None
            
            log.info(f"[ MEDIA ] Video uploaded: {video_url}")
            return video_url
            
        except Exception as e:
            log.error(f"[ MEDIA ] Upload error: {e}", exc_info=True)
            return None
            
        finally:
            # Clean up video file
            self.storage.cleanup_videos(video_path)
    
    async def _generate_video_async(self) -> Optional[str]:
        """
        Generate video asynchronously in thread pool
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._generate_video_sync
        )
    
    def _generate_video_sync(self) -> Optional[str]:
        """
        Synchronous video generation (runs in thread pool)
        """
        with self.video_generation_lock:
            # Get images
            images = self.storage.get_images()
            
            if len(images) < self.min_images:
                log.warning(f"[ MEDIA ] Not enough images: {len(images)}/{self.min_images}")
                return None
            
            # Get output path
            output_path = self.storage.get_video_path()
            
            try:
                # Generate video
                success = self.video_gen.generate(images, output_path)
                
                if not success:
                    return None
                
                # Clean up source images
                self.storage.cleanup_images(images)
                
                return output_path
                
            except Exception as e:
                log.error(f"[ MEDIA ] Video generation failed: {e}", exc_info=True)
                return None
