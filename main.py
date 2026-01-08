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

        # Test Facebook connection first
        self.redis = await redis.init_redis()
        
        self.fb_uploader = FacebookUploader(
            page_id=config.PAGE_ID,
            page_access_token=config.PAGE_ACCESS_TOKEN,
        )
        
        self.storage = R2UploaderService(
            account_id=config.R2_ACCOUNT_ID,
            access_key=config.R2_ACCESS_KEY,
            secret_key=config.R2_SECRET_KEY
        )
        
        self.ig_uploader = InstagramUploader(
            ig_page_id=config.PAGE_ID,
            access_token=config.PAGE_ACCESS_TOKEN
        )

        
        loop = asyncio.get_running_loop()
        
        connection_ok = await loop.run_in_executor(
            None,
            self.fb_uploader.test_connection,
        )
        
        if not connection_ok:
            log.warning("[ AUTO UPLOADER ] Facebook connection failed")
            

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
        
        
            video_ready payload = {
                "type": "video_ready",
                "source": "video_worker",
                "timestamp": payload.get("timestamp"),
                "video": {
                    "path": video_url,
                    "format": "mp4",
                },
            }
            
            job_vacancy payload = { 
            "type": "job_vacancy", 
            "source": payload.get("source"), 
            "timestamp": payload.get("timestamp"), 
            "caption": payload.get("caption"), 
            "image": image_base64, "extracted_data": extracted_data, } 

            extracted_data sample = { 
            "is_job_vacancy": true, 
            "email": ["recruitment@startup.id"], 
            "position": "Backend Developer", 
            "subject_email": "Backend Developer - {{name}} - {{phone}}", "gender_required": null }
        
        """
        if payload.get("type") == "video_ready":
            video = payload.get("video", {})
            video_url = video.get("path")
            
            if not video_url:
                log.warning("[ VIDEO URL ] -- video path not found")
                return
            
            loop = asyncio.get_running_loop()

            try:
                if self.fb_uploader:
                    await loop.run_in_executor(
                        None,
                        self.fb_uploader.upload_video_from_url,
                        video_url,
                        "Rangkuman informasi lowongan kerja hari ini",
                        "INFO LOWONGAN KERJA HARI INI",
                    )
                    await asyncio.sleep(30)
            finally:
                if self.storage:
                    await loop.run_in_executor(
                        None,
                        self.storage.clean_video,
                        video_url
                    )
                    
            return

        
        extracted = self._validate_job_vacancy_payload(payload)
        if not extracted:
            return
        
        allowed = await can_post_today(
            self.redis,
            prefix="facebook:daily_posts",
        )
        
        if not allowed:
            log.debug("[ REDIS LIMIT ] -- redis reach limit")
            return

        image_base64 = payload.get("image")

        if image_base64 is not None:
            
            try:
                loop = asyncio.get_running_loop()
                
                position: str | None = extracted.get("position")
                emails: list[str] | None = extracted.get("email")
                gender_required: str | None = extracted.get("gender_required")
                
                # upload to r2 storage
                if self.storage:
                    image_url = await loop.run_in_executor(
                        None,
                        self.storage.upload_base64_image,
                        image_base64,
                    )
                
                
                # upload to fb page
                if self.fb_uploader:
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
                    await increment_daily_post(
                        self.redis,
                        prefix="facebook:daily_posts",
                        )
                    
                            
                # if self.ig_uploader:
                #     await loop.run_in_executor(
                #         None,
                #         self.ig_uploader.upload_image,
                #         position,
                #         emails,
                #         gender_required,
                #         image_url,
                #     )

                #     log.info("[ INSTAGRAM ] Upload success")

            except Exception as e:
                log.error(
                    f"[ AUTO UPLOADER ] Failed to upload to Facebook: {e}",
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