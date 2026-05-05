## services/instagram_client.py

import asyncio
import logging
from typing import Optional, Dict, Any, List

import httpx

from services.utils.caption_builder import build_job_caption
from services.utils.retry import async_retry

log = logging.getLogger(__name__)

API_VERSION = "v25.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

# httpx retryable exceptions
RETRYABLE = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    ConnectionError,
    TimeoutError,
)


class InstagramUploader:
    def __init__(
        self,
        instagram_id: str,
        access_token: str,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
    ):
        self.ig_user_id = instagram_id
        self.token = access_token
        self.base_url = base_url
        self.timeout = httpx.Timeout(connect=10.0, read=timeout, write=timeout, pool=10.0)
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create shared async HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client
    
    async def close(self) -> None:
        """Close the HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ==========================================================
    # Step 1: Create Media Container (IMAGE)
    # ==========================================================
    async def _create_image_container(
        self,
        image_url: str,
        caption: str,
    ) -> str:
        url = f"{self.base_url}/{self.ig_user_id}/media"
        client = await self._get_client()

        resp = await client.post(
            url,
            data={
                "image_url": image_url,
                "caption": caption,
                "access_token": self.token,
            },
        )

        if resp.status_code != 200:
            log.error(f"[ INSTAGRAM ] Media container failed: {resp.text}")
            resp.raise_for_status()

        return resp.json()["id"]

    # ==========================================================
    # Step 2: Check Media Status (for video)
    # ==========================================================
    async def _check_media_status(
        self, 
        creation_id: str, 
        max_attempts: int = 30,
        wait_seconds: int = 10
    ) -> bool:
        """
        Check if media container is ready to publish.
        Returns True when ready, False if timeout.
        """
        url = f"{self.base_url}/{creation_id}"
        client = await self._get_client()

        for attempt in range(max_attempts):
            try:
                resp = await client.get(
                    url,
                    params={
                        "fields": "status_code",
                        "access_token": self.token,
                    },
                )

                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("status_code")

                    log.info(f"[ INSTAGRAM ] Media status check {attempt + 1}/{max_attempts}: {status}")

                    if status == "FINISHED":
                        return True
                    elif status == "ERROR":
                        log.error("[ INSTAGRAM ] Media processing error")
                        return False

            except Exception as e:
                log.warning(f"[ INSTAGRAM ] Status check error: {e}")

            if attempt < max_attempts - 1:
                await asyncio.sleep(wait_seconds)

        log.warning(f"[ INSTAGRAM ] Media not ready after {max_attempts * wait_seconds}s")
        return False

    # ==========================================================
    # Step 3: Publish Media
    # ==========================================================
    async def _publish_media(self, creation_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/{self.ig_user_id}/media_publish"
        client = await self._get_client()

        resp = await client.post(
            url,
            data={
                "creation_id": creation_id,
                "access_token": self.token,
            },
        )

        if resp.status_code != 200:
            log.error(f"[ INSTAGRAM ] Publish failed: {resp.text}")
            resp.raise_for_status()

        return resp.json()

    # ==========================================================
    # Public API: Upload Image
    # ==========================================================
    @async_retry(max_retries=2, base_delay=2.0, retryable_exceptions=RETRYABLE)
    async def upload_image(
        self,
        position: Optional[str] = None,
        emails: Optional[List[str]] = None,
        gender_required: Optional[str] = None,
        public_image_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload image to Instagram Feed.
        Instagram requires a publicly accessible image URL.
        """
        caption = build_job_caption(
            position=position,
            emails=emails,
            gender_required=gender_required,
        )

        if not public_image_url:
            raise ValueError("Instagram Graph API requires public image_url")

        log.info("[ INSTAGRAM ] Creating image media container")

        creation_id = await self._create_image_container(
            image_url=public_image_url,
            caption=caption,
        )

        # Images usually process quickly, small delay is enough
        await asyncio.sleep(2)

        log.info("[ INSTAGRAM ] Publishing image media")

        result = await self._publish_media(creation_id)

        log.info(f"[ INSTAGRAM ] Image upload success: media_id={result.get('id')}")
        return result

    # ==========================================================
    # Public API: Upload Video (Reels)
    # ==========================================================
    @async_retry(max_retries=2, base_delay=5.0, retryable_exceptions=RETRYABLE)
    async def upload_video(
        self,
        video_url: str,
        caption: str,
        max_wait_minutes: int = 5,
    ) -> Dict[str, Any]:
        """
        Upload video (Reels).
        video_url MUST be publicly accessible.
        
        Args:
            video_url: Public URL to video file
            caption: Caption for the reel
            max_wait_minutes: Maximum minutes to wait for video processing
        """
        log.info("[ INSTAGRAM ] Creating video media container")

        url = f"{self.base_url}/{self.ig_user_id}/media"
        client = await self._get_client()

        video_timeout = httpx.Timeout(connect=10.0, read=120.0, write=120.0, pool=10.0)
        resp = await client.post(
            url,
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "access_token": self.token,
            },
            timeout=video_timeout,
        )

        if resp.status_code != 200:
            log.error(f"[ INSTAGRAM ] Video container failed: {resp.text}")
            resp.raise_for_status()

        creation_id = resp.json()["id"]
        log.info(f"[ INSTAGRAM ] Video container created: {creation_id}")

        # Wait for video to be processed
        log.info("[ INSTAGRAM ] Waiting for video processing...")
        max_attempts = (max_wait_minutes * 60) // 10

        is_ready = await self._check_media_status(
            creation_id, 
            max_attempts=max_attempts,
            wait_seconds=10
        )

        if not is_ready:
            raise RuntimeError(
                f"Video not ready after {max_wait_minutes} minutes. "
                "Try again later or check video format/size."
            )

        log.info("[ INSTAGRAM ] Video ready, publishing...")
        result = await self._publish_media(creation_id)

        log.info(f"[ INSTAGRAM ] Video upload success: media_id={result.get('id')}")
        return result

    # ==========================================================
    # Test Connection
    # ==========================================================
    async def test_connection(self) -> bool:
        url = f"{self.base_url}/{self.ig_user_id}"

        try:
            client = await self._get_client()
            resp = await client.get(
                url,
                params={
                    "fields": "id,username",
                    "access_token": self.token,
                },
            )
            resp.raise_for_status()

            data = resp.json()
            log.info(f"[ INSTAGRAM ] Connection OK: @{data.get('username')}")
            return True

        except Exception as e:
            log.error(f"[ INSTAGRAM ] Connection failed: {e}")
            return False