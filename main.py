# main.py

import logging
import asyncio
import signal
from typing import Optional

from core import redis
from config.logger import setup_logging
from config.settings import config

from services import (
    RedisSubscriber,
    FacebookUploader,
    InstagramUploader,
    R2UploaderService,
    can_post_today,
    increment_daily_post,
)

setup_logging()

log = logging.getLogger(__name__)

class AutoUploader:
    def __init__(self):
        
        self.shutdown_event = asyncio.Event()
        self.shutdown_lock = asyncio.Lock()
        self.stopped = False
        self.redis = None
        self.storage = None
        
        self.subscriber: Optional[RedisSubscriber] = None
        self.stats_task : Optional[R2UploaderService] = None
        self.fb_uploader : Optional[FacebookUploader] = None
        self.ig_uploader: Optional[InstagramUploader] = None


    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()
   
    async def start(self):
        log.info("[ AUTO UPLOADER ] Starting up...")

        # Initialize Redis
        self.redis = await redis.init_redis()
        
        # Initialize Facebook Uploader
        # self.fb_uploader = FacebookUploader(
        #     page_id=config.FACEBOOK_PAGE_ID,  # Fixed: consistent naming
        #     page_access_token=config.FB_ACCESS_TOKEN,  # Fixed: use dedicated token
        # )
        
        self.fb_uploader = None
        
        # Initialize R2 Storage
        self.storage = R2UploaderService(
            account_id=config.R2_ACCOUNT_ID,
            access_key=config.R2_ACCESS_KEY,
            secret_key=config.R2_SECRET_KEY
        )
        
        # Initialize Instagram Uploader
        self.ig_uploader = InstagramUploader(
            instagram_id=config.INSTAGRAM_ID,
            access_token=config.IG_ACCESS_TOKEN  # Fixed: use dedicated token
        )

        # Test connections
        loop = asyncio.get_running_loop()
        
        # Test Facebook connection
        
        if self.fb_uploader:
            fb_ok = await loop.run_in_executor(
                None,
                self.fb_uploader.test_connection,
            )
        
            if not fb_ok:
                log.warning("[ AUTO UPLOADER ] Facebook connection failed")
                self.fb_uploader = None
        
        # Test Instagram connection
        if self.ig_uploader:
            ig_ok = await loop.run_in_executor(
                None,
                self.ig_uploader.test_connection,
            )
            
            if not ig_ok:
                log.warning("[ AUTO UPLOADER ] Instagram connection failed")
                self.ig_uploader = None

        # Start Redis subscriber
        self.subscriber = RedisSubscriber(
            redis_client=self.redis,
            channel=config.REDIS_CHANNEL,
            message_handler=self._handle_payload,
            shutdown_event=self.shutdown_event,
        )
        await self.subscriber.start()
        
        log.info("[ AUTO UPLOADER ] Startup complete")

    async def stop(self):
        async with self.shutdown_lock:
            if self.stopped:
                return
            self.stopped = True

        log.info("[ AUTO UPLOADER ] Shutting down...")
    
        self.shutdown_event.set()

        if self.subscriber:
            await self.subscriber.stop()

        await redis.close_redis()

        log.info("[ AUTO UPLOADER ] Shutdown complete")
        
    def _validate_job_vacancy_payload(self, payload: dict) -> dict | None:
        """
        Validate and extract job vacancy payload.
        Return extracted_data if valid, otherwise None.
        """
        if payload.get("type") != "job_vacancy":
            log.debug("[ AUTO UPLOADER ] Skipping non-job_vacancy message")
            return None

        extracted = payload.get("extracted_data")
        if not extracted:
            log.warning("[ AUTO UPLOADER ] Empty payload")
            return None

        if not extracted.get("is_job_vacancy"):
            log.debug("[ AUTO UPLOADER ] Not a job vacancy")
            return None

        image_base64 = payload.get("image")
        if not image_base64:
            log.warning("[ AUTO UPLOADER ] No image in payload - skipping")
            return None

        return extracted

    async def _handle_payload(self, payload: dict):
        """
        Handle incoming job vacancy payload from Redis
        
        Payload types:
        
        1. video_ready payload = {
            "type": "video_ready",
            "source": "video_worker",
            "timestamp": payload.get("timestamp"),
            "video": {
                "path": video_url,
                "format": "mp4",
            },
        }
        
        2. job_vacancy payload = {
            "type": "job_vacancy",
            "source": payload.get("source"),
            "timestamp": payload.get("timestamp"),
            "caption": payload.get("caption"),
            "image": image_base64,
            "extracted_data": extracted_data,
        }

        extracted_data sample = {
            "is_job_vacancy": true,
            "email": ["recruitment@startup.id"],
            "position": "Backend Developer",
            "subject_email": "Backend Developer - {{name}} - {{phone}}",
            "gender_required": null
        }
        """
        
        # ================================================================
        # Handle Video Ready
        # ================================================================
        if payload.get("type") == "video_ready":
            video = payload.get("video", {})
            video_url = video.get("path")
            
            if not video_url:
                log.warning("[ AUTO UPLOADER ] Video ready but no path provided")
                return
            
            loop = asyncio.get_running_loop()
            
            video_caption = "🎬 Rangkuman informasi lowongan kerja hari ini\n\n#lowongankerja #loker #jobvacancy"
            video_title = "INFO LOWONGAN KERJA HARI INI"

            # Upload to Facebook
            try:
                if self.fb_uploader:
                    log.info("[ AUTO UPLOADER ] Uploading video to Facebook...")
                    await loop.run_in_executor(
                        None,
                        self.fb_uploader.upload_video_from_url,
                        video_url,
                        video_caption,
                        video_title,
                    )
                    log.info("[ AUTO UPLOADER ] Facebook video upload complete")
                    
                    # Wait before Instagram upload to avoid rate limits
                    await asyncio.sleep(30)
                    
            except Exception as e:
                log.error(f"[ AUTO UPLOADER ] Facebook video upload failed: {e}", exc_info=True)
            
            # Upload to Instagram (Reels)
            try:
                if self.ig_uploader:
                    log.info("[ AUTO UPLOADER ] Uploading video to Instagram (Reels)...")
                    await loop.run_in_executor(
                        None,
                        self.ig_uploader.upload_video,
                        video_url,
                        video_caption,
                        5,  # max_wait_minutes
                    )
                    log.info("[ AUTO UPLOADER ] Instagram reels upload complete")
                    
            except Exception as e:
                log.error(f"[ AUTO UPLOADER ] Instagram video upload failed: {e}", exc_info=True)
            
            # Clean up video from R2
            finally:
                try:
                    if self.storage:
                        log.info("[ AUTO UPLOADER ] Cleaning up video from R2...")
                        await loop.run_in_executor(
                            None,
                            self.storage.clean_video,
                            video_url
                        )
                        log.info("[ AUTO UPLOADER ] Video cleanup complete")
                except Exception as e:
                    log.error(f"[ AUTO UPLOADER ] Video cleanup failed: {e}", exc_info=True)
                    
            return

        # ================================================================
        # Handle Job Vacancy (Image Post)
        # ================================================================
        data = self._validate_job_vacancy_payload(payload)
        if not data:
            return
        
        # Check daily post limit
        allowed = await can_post_today(
            self.redis,
            prefix="facebook:daily_posts",
        )
        
        if not allowed:
            log.warning("[ AUTO UPLOADER ] Daily post limit reached")
            return

        image_base64 = payload.get("image")

        if image_base64 is None:
            log.warning("[ AUTO UPLOADER ] No image in payload")
            return
            
        try:
            loop = asyncio.get_running_loop()
            
            position: str | None = data.get("position")
            emails: list[str] | None = data.get("email")
            gender_required: str | None = data.get("gender_required")
            
            image_url = None
            
            # Upload to R2 storage (for Instagram)
            try:
                if self.storage:
                    log.info("[ AUTO UPLOADER ] Uploading image to R2...")
                    image_url = await loop.run_in_executor(
                        None,
                        self.storage.upload_base64_image,
                        image_base64,
                    )
                    log.info(f"[ AUTO UPLOADER ] R2 upload success: {image_url}")
            except Exception as e:
                log.error(f"[ AUTO UPLOADER ] R2 upload failed: {e}", exc_info=True)
            
            # Upload to Facebook Page
            fb_success = False
            try:
                if self.fb_uploader:
                    log.info("[ AUTO UPLOADER ] Uploading to Facebook...")
                    result = await loop.run_in_executor(
                        None,
                        self.fb_uploader.upload_image,
                        image_base64,
                        position,
                        emails,
                        gender_required,
                    )

                    post_id = result.get("post_id") or result.get("id")
                    if post_id:
                        fb_success = True
                        log.info(f"[ AUTO UPLOADER ] Facebook upload success: {post_id}")
                        
                        # Increment daily post counter
                        await increment_daily_post(
                            self.redis,
                            prefix="facebook:daily_posts",
                        )
            except Exception as e:
                log.error(f"[ AUTO UPLOADER ] Facebook upload failed: {e}", exc_info=True)
            
            # Upload to Instagram (only if R2 upload succeeded)
            try:
                if self.ig_uploader and image_url:
                    log.info("[ AUTO UPLOADER ] Uploading to Instagram...")
                    
                    # Wait a bit to avoid rate limits
                    if fb_success:
                        await asyncio.sleep(5)
                    
                    result = await loop.run_in_executor(
                        None,
                        self.ig_uploader.upload_image,
                        position,
                        emails,
                        gender_required,
                        image_url,
                    )
                    
                    media_id = result.get("id")
                    log.info(f"[ AUTO UPLOADER ] Instagram upload success: {media_id}")
                    
                elif not image_url:
                    log.warning("[ AUTO UPLOADER ] Skipping Instagram upload - no public image URL")
                    
            except Exception as e:
                log.error(f"[ AUTO UPLOADER ] Instagram upload failed: {e}", exc_info=True)

        except Exception as e:
            log.error(
                f"[ AUTO UPLOADER ] Failed to process job vacancy: {e}",
                exc_info=True
            )
    
async def main():
    shutdown_event = asyncio.Event()
    
    def signal_handler(sig):
        log.info(f"[ AUTO UPLOADER ] Received signal {sig}, initiating shutdown...")
        shutdown_event.set()
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
    
    try:
        async with AutoUploader():
            log.info("[ AUTO UPLOADER ] Running...")
            await shutdown_event.wait()
            log.info("[ AUTO UPLOADER ] Shutdown signal received")
    except Exception as e:
        log.error(f"[ AUTO UPLOADER ] Error: {e}", exc_info=True)
    finally:
        log.info("[ AUTO UPLOADER ] Exiting...")

if __name__ == "__main__":
    asyncio.run(main())
