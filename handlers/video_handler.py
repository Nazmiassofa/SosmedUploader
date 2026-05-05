## handlers/video_handler.py
"""
Handles video_ready payloads — upload to Instagram Reels and Facebook.
"""

import logging
import asyncio
from typing import Optional

from services.instagram_client import InstagramUploader
from services.facebook_client import FacebookUploader
from services.r2_service import R2UploaderService

log = logging.getLogger(__name__)

VIDEO_CAPTION = "🎬 Rangkuman informasi lowongan kerja hari ini\n\n#lowongankerja #loker #jobvacancy"


class VideoHandler:
    """Handles uploading videos to social media platforms and cleanup."""

    def __init__(
        self,
        ig_uploader: Optional[InstagramUploader],
        fb_uploader: Optional[FacebookUploader],
        storage: Optional[R2UploaderService],
    ):
        self.ig_uploader = ig_uploader
        self.fb_uploader = fb_uploader
        self.storage = storage

    async def handle(self, video_url: str) -> None:
        """
        Upload video to Instagram and Facebook, then clean up from R2.
        
        The entire flow is wrapped in try/finally to guarantee cleanup
        regardless of which upload succeeds or fails.
        """
        try:
            # Upload to Instagram (Reels)
            if self.ig_uploader:
                try:
                    log.info("[ VIDEO HANDLER ] Uploading video to Instagram (Reels)...")
                    await self.ig_uploader.upload_video(
                        video_url,
                        VIDEO_CAPTION,
                        max_wait_minutes=5,
                    )
                    log.info("[ VIDEO HANDLER ] Instagram reels upload complete")
                except Exception as e:
                    log.error(f"[ VIDEO HANDLER ] Instagram video upload failed: {e}", exc_info=True)

            # Upload to Facebook
            if self.fb_uploader:
                try:
                    log.info("[ VIDEO HANDLER ] Uploading video to Facebook...")
                    await self.fb_uploader.upload_video_from_url(
                        video_url,
                        VIDEO_CAPTION,
                        "Rangkuman Lowongan Kerja Hari Ini",
                    )
                    log.info("[ VIDEO HANDLER ] Facebook video upload complete")
                except Exception as e:
                    log.error(f"[ VIDEO HANDLER ] Facebook video upload failed: {e}", exc_info=True)

        finally:
            # Always clean up video from R2
            if self.storage:
                try:
                    log.info("[ VIDEO HANDLER ] Cleaning up video from R2...")
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None,
                        self.storage.clean_video,
                        video_url,
                    )
                    log.info("[ VIDEO HANDLER ] Video cleanup complete")
                except Exception as e:
                    log.error(f"[ VIDEO HANDLER ] Video cleanup failed: {e}", exc_info=True)
