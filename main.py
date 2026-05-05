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
    InstagramUploader,
    R2UploaderService,
    FacebookUploader,
    MediaService,
)
from services.media import ImageProcessor

from handlers import JobVacancyHandler, VideoHandler

setup_logging()

log = logging.getLogger(__name__)


class AutoUploader:
    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self.shutdown_lock = asyncio.Lock()
        self.stopped = False
        self.redis = None
        self.storage: Optional[R2UploaderService] = None

        self.subscriber: Optional[RedisSubscriber] = None
        self.ig_uploader: Optional[InstagramUploader] = None
        self.fb_uploader: Optional[FacebookUploader] = None
        self.image_processor: Optional[ImageProcessor] = None
        self.media: Optional[MediaService] = None

        # Handlers
        self.job_handler: Optional[JobVacancyHandler] = None
        self.video_handler: Optional[VideoHandler] = None

        # Prevent concurrent video generation
        self._video_gen_lock = asyncio.Lock()
        self._video_generating = False

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    async def start(self):
        log.info("[ AUTO UPLOADER ] Starting up...")

        # Initialize Redis
        self.redis = await redis.init_redis()

        self.image_processor = ImageProcessor(target_mode="auto")

        # Initialize R2 Storage (single instance for all services)
        self.storage = R2UploaderService(
            account_id=config.R2_ACCOUNT_ID,
            access_key=config.R2_ACCESS_KEY,
            secret_key=config.R2_SECRET_KEY,
            bucket=config.R2_BUCKET,
            public_base_url=config.R2_BASE_URL,
        )

        # Initialize Facebook Uploader
        self.fb_uploader = FacebookUploader(
            page_id=config.FACEBOOK_PAGE_ID,
            access_token=config.FACEBOOK_ACCESS_TOKEN,
        )

        # Initialize Instagram Uploader
        self.ig_uploader = InstagramUploader(
            instagram_id=config.INSTAGRAM_ID,
            access_token=config.INSTAGRAM_ACCESS_TOKEN,
        )

        # Test connections (async now)
        if self.fb_uploader:
            fb_ok = await self.fb_uploader.test_connection()
            if not fb_ok:
                log.warning("[ AUTO UPLOADER ] Facebook connection failed")
                self.fb_uploader = None

        if self.ig_uploader:
            ig_ok = await self.ig_uploader.test_connection()
            if not ig_ok:
                log.warning("[ AUTO UPLOADER ] Instagram connection failed")
                self.ig_uploader = None

        # Initialize handlers
        self.video_handler = VideoHandler(
            ig_uploader=self.ig_uploader,
            fb_uploader=self.fb_uploader,
            storage=self.storage,
        )

        self.job_handler = JobVacancyHandler(
            redis=self.redis,
            ig_uploader=self.ig_uploader,
            fb_uploader=self.fb_uploader,
            storage=self.storage,
            image_processor=self.image_processor,
        )

        # Start Redis subscriber
        self.subscriber = RedisSubscriber(
            redis_client=self.redis,
            channel=config.REDIS_CHANNEL,
            message_handler=self._handle_payload,
            shutdown_event=self.shutdown_event,
        )
        await self.subscriber.start()

        # Initialize Media Service (shares R2 instance)
        self.media = MediaService(
            uploader=self.storage,
            min_images=10,
            duration_per_image=4.0,
        )

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

        if self.media:
            await self.media.cleanup()

        # Close HTTP clients
        if self.ig_uploader:
            await self.ig_uploader.close()
        if self.fb_uploader:
            await self.fb_uploader.close()

        await redis.close_redis()

        log.info("[ AUTO UPLOADER ] Shutdown complete")

    async def _handle_payload(self, payload: dict):
        """Route incoming payloads to appropriate handler."""

        # Handle Video Ready
        if payload.get("type") == "video_ready":
            video = payload.get("video", {})
            video_url = video.get("path")

            if not video_url:
                log.warning("[ AUTO UPLOADER ] Video ready but no path provided")
                return

            if self.video_handler:
                await self.video_handler.handle(video_url)
            return  # ← Fix: don't fall through to job_vacancy

        # Handle Job Vacancy (Image Post)
        if not self.job_handler:
            return

        data = self.job_handler.validate_payload(payload)
        if not data:
            return

        # Save image for video generation
        image_base64 = payload.get("image")
        if self.media and image_base64:
            saved = await self.media.save_image(image_base64)
            if saved:
                log.debug("[ AUTO UPLOADER ] Image saved for video generation")

                if self.media.should_generate_video():
                    await self._try_generate_video()

        # Process and upload job vacancy
        await self.job_handler.handle(payload, data)

    async def _try_generate_video(self):
        """Trigger video generation with race-condition protection."""
        async with self._video_gen_lock:
            if self._video_generating:
                log.debug("[ AUTO UPLOADER ] Video generation already in progress, skipping")
                return
            self._video_generating = True

        log.info("[ AUTO UPLOADER ] Enough images collected, triggering video generation...")
        asyncio.create_task(self._generate_and_publish_video())

    async def _generate_and_publish_video(self):
        """Background task to generate video and trigger posting."""
        try:
            start_time = asyncio.get_running_loop().time()

            if not self.media:
                return

            video_url = await self.media.generate_and_upload_video()

            if not video_url:
                log.error("[ AUTO UPLOADER ] Failed to generate video")
                return

            duration = asyncio.get_running_loop().time() - start_time
            log.info(f"[ AUTO UPLOADER ] Video generated in {duration:.2f}s: {video_url}")

            if self.video_handler:
                await self.video_handler.handle(video_url)

        except Exception as e:
            log.error(f"[ AUTO UPLOADER ] Error in background video task: {e}", exc_info=True)
        finally:
            self._video_generating = False


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
