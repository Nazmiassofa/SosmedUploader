## handlers/job_vacancy_handler.py
"""
Handles job_vacancy payloads — image processing, upload to Instagram & Facebook.
"""

import logging
import asyncio
from typing import Optional

from redis.asyncio import Redis

from services.instagram_client import InstagramUploader
from services.facebook_client import FacebookUploader
from services.r2_service import R2UploaderService
from services.media.image_processor import ImageProcessor
from services.redis_limits import can_post_today, increment_daily_post

log = logging.getLogger(__name__)


class JobVacancyHandler:
    """Handles processing and uploading job vacancy posts."""

    def __init__(
        self,
        redis: Redis,
        ig_uploader: Optional[InstagramUploader],
        fb_uploader: Optional[FacebookUploader],
        storage: Optional[R2UploaderService],
        image_processor: Optional[ImageProcessor],
    ):
        self.redis = redis
        self.ig_uploader = ig_uploader
        self.fb_uploader = fb_uploader
        self.storage = storage
        self.image_processor = image_processor

    def validate_payload(self, payload: dict) -> dict | None:
        """
        Validate and extract job vacancy payload.
        Returns extracted_data if valid, otherwise None.
        """
        if payload.get("type") != "job_vacancy":
            log.debug("[ JOB HANDLER ] Skipping non-job_vacancy message")
            return None

        extracted = payload.get("extracted_data")
        if not extracted:
            log.warning("[ JOB HANDLER ] Empty payload")
            return None

        if not extracted.get("is_job_vacancy"):
            log.debug("[ JOB HANDLER ] Not a job vacancy")
            return None

        image_base64 = payload.get("image")
        image_url = payload.get("image_url")
        if not image_base64 and not image_url:
            log.warning("[ JOB HANDLER ] No image or image_url in payload — skipping")
            return None

        return extracted

    async def handle(self, payload: dict, data: dict) -> None:
        """
        Process and upload job vacancy to social media.
        
        Args:
            payload: Full Redis payload
            data: Validated extracted_data from payload
        """
        # Check per-platform daily limits
        ig_allowed = await can_post_today(
            self.redis, prefix="instagram:daily_posts"
        )
        fb_allowed = await can_post_today(
            self.redis, prefix="facebook:daily_posts"
        )

        if not ig_allowed and not fb_allowed:
            log.warning("[ JOB HANDLER ] Daily post limit reached for all platforms")
            return

        image_base64 = payload.get("image")
        image_url = payload.get("image_url")

        position: str | None = data.get("position")
        emails: list[str] | None = data.get("email")
        gender_required: str | None = data.get("gender_required")

        try:
            # ============================================================
            # STEP 1: Get public image URL
            # ============================================================
            if image_url:
                log.info(f"[ JOB HANDLER ] Using provided public URL: {image_url}")
            elif image_base64:
                # Process image if needed for Instagram
                image_url = await self._process_and_upload_image(image_base64)
                if not image_url:
                    return
            else:
                log.warning("[ JOB HANDLER ] No image or URL to post")
                return

            # ============================================================
            # STEP 2: Upload to Instagram
            # ============================================================
            if self.ig_uploader and image_url and ig_allowed:
                try:
                    log.info("[ JOB HANDLER ] Uploading to Instagram...")
                    result = await self.ig_uploader.upload_image(
                        position=position,
                        emails=emails,
                        gender_required=gender_required,
                        public_image_url=image_url,
                    )

                    media_id = result.get("id")
                    if media_id:
                        await increment_daily_post(
                            self.redis, prefix="instagram:daily_posts"
                        )
                        log.info(f"[ JOB HANDLER ] Instagram upload success: {media_id}")
                    else:
                        log.warning("[ JOB HANDLER ] Instagram upload returned no media_id")

                except Exception as e:
                    log.error(f"[ JOB HANDLER ] Instagram upload failed: {e}", exc_info=True)

            elif not ig_allowed:
                log.info("[ JOB HANDLER ] Instagram daily limit reached, skipping")

            # ============================================================
            # STEP 3: Upload to Facebook
            # ============================================================
            if self.fb_uploader and fb_allowed:
                try:
                    if image_url:
                        log.info("[ JOB HANDLER ] Uploading to Facebook via URL...")
                        result = await self.fb_uploader.upload_image_from_url(
                            image_url=image_url,
                            position=position,
                            emails=emails,
                            gender_required=gender_required,
                        )
                    elif image_base64:
                        log.info("[ JOB HANDLER ] Uploading to Facebook via base64...")
                        result = await self.fb_uploader.upload_image(
                            image_base64=image_base64,
                            position=position,
                            emails=emails,
                            gender_required=gender_required,
                        )

                    fb_id = result.get("id") or result.get("post_id")
                    if fb_id:
                        await increment_daily_post(
                            self.redis, prefix="facebook:daily_posts"
                        )
                        log.info(f"[ JOB HANDLER ] Facebook upload success: {fb_id}")

                except Exception as e:
                    log.error(f"[ JOB HANDLER ] Facebook upload failed: {e}", exc_info=True)

            elif not fb_allowed:
                log.info("[ JOB HANDLER ] Facebook daily limit reached, skipping")

        except Exception as e:
            log.error(f"[ JOB HANDLER ] Failed to process job vacancy: {e}", exc_info=True)

    async def _process_and_upload_image(self, image_base64: str) -> Optional[str]:
        """
        Process image for Instagram compliance and upload to R2.
        Returns public URL or None on failure.
        """
        loop = asyncio.get_running_loop()
        processed_bytes = None

        try:
            if self.image_processor:
                log.info("[ JOB HANDLER ] Processing image for Instagram...")

                # Get image info and process in executor (CPU-bound PIL work)
                image_info = await loop.run_in_executor(
                    None,
                    self.image_processor.get_image_info,
                    image_base64,
                )

                log.info(
                    f"[ JOB HANDLER ] Original image: "
                    f"{image_info.get('width')}x{image_info.get('height')} "
                    f"(ratio: {image_info.get('aspect_ratio', 0):.2f})"
                )

                if not image_info.get("is_valid_for_instagram"):
                    log.info("[ JOB HANDLER ] Image needs processing for Instagram")

                    # Process and get raw bytes directly — no base64 round-trip
                    import base64 as b64
                    raw_bytes = b64.b64decode(image_base64)
                    processed_bytes = await loop.run_in_executor(
                        None,
                        self.image_processor.process_image_bytes,
                        raw_bytes,
                        "pad",
                        95,
                    )
                    del raw_bytes

                    log.info("[ JOB HANDLER ] Image processing complete")
                else:
                    log.info("[ JOB HANDLER ] Image already valid, skipping processing")

        except Exception as e:
            log.error(f"[ JOB HANDLER ] Image processing failed: {e}", exc_info=True)
            log.warning("[ JOB HANDLER ] Continuing with original image...")

        # Upload to R2
        try:
            if not self.storage:
                log.error("[ JOB HANDLER ] R2 storage not initialized")
                return None

            if processed_bytes:
                # Upload processed bytes directly
                image_url = await loop.run_in_executor(
                    None,
                    self.storage.upload_image_bytes,
                    processed_bytes,
                )
            else:
                # Upload original base64
                image_url = await loop.run_in_executor(
                    None,
                    self.storage.upload_base64_image,
                    image_base64,
                )

            log.info(f"[ JOB HANDLER ] R2 upload success: {image_url}")
            return image_url

        except Exception as e:
            log.error(f"[ JOB HANDLER ] R2 upload failed: {e}", exc_info=True)
            return None

        finally:
            if processed_bytes is not None:
                del processed_bytes
