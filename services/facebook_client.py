## services/facebook_client.py

import base64
import logging
from io import BytesIO
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


class FacebookUploader:
    def __init__(
        self,
        page_id: str,
        access_token: str,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
    ):  
        self.page_id = page_id
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
    # Upload Video from URL
    # ==========================================================
    @async_retry(max_retries=2, base_delay=5.0, retryable_exceptions=RETRYABLE)
    async def upload_video_from_url(
        self,
        video_url: str,
        description: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload video to Facebook Page using remote URL.

        Args:
            video_url: Publicly accessible video URL (mp4 recommended)
            description: Video description / caption
            title: Video title

        Returns:
            Facebook API response
        """
        if not video_url.startswith(("http://", "https://")):
            raise ValueError("video_url must be a valid public URL")

        url = f"{self.base_url}/{self.page_id}/videos"

        data = {
            "access_token": self.token,
            "file_url": video_url,
        }

        if description:
            data["description"] = description
        if title:
            data["title"] = title

        log.info(f"[ FACEBOOK ] Uploading video from URL: {video_url}")

        client = await self._get_client()
        video_timeout = httpx.Timeout(connect=10.0, read=120.0, write=120.0, pool=10.0)
        
        resp = await client.post(url, data=data, timeout=video_timeout)

        if resp.status_code != 200:
            log.error(
                f"[ FACEBOOK ] Video URL upload failed: "
                f"{resp.status_code} - {resp.text}"
            )

        resp.raise_for_status()
        result = resp.json()

        log.info(f"[ FACEBOOK ] Video URL upload successful: video_id={result.get('id')}")
        return result

    # ==========================================================
    # Upload Image from URL
    # ==========================================================
    @async_retry(max_retries=2, base_delay=2.0, retryable_exceptions=RETRYABLE)
    async def upload_image_from_url(
        self,
        image_url: str,
        position: Optional[str] = None,
        emails: Optional[List[str]] = None,
        gender_required: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload image to Facebook Page using a public URL"""
        if not image_url.startswith(("http://", "https://")):
            raise ValueError("image_url must be a valid public URL")

        url = f"{self.base_url}/{self.page_id}/photos"

        formatted_caption = build_job_caption(
            position=position,
            emails=emails,
            gender_required=gender_required,
        )

        data = {
            "access_token": self.token,
            "url": image_url,
            "message": formatted_caption,
        }

        log.info(f"[ FACEBOOK ] Uploading image from URL: {image_url}")

        client = await self._get_client()
        resp = await client.post(url, data=data)

        if resp.status_code != 200:
            log.error(
                f"[ FACEBOOK ] Image URL upload failed: "
                f"{resp.status_code} - {resp.text}"
            )

        resp.raise_for_status()
        result = resp.json()

        log.info(f"[ FACEBOOK ] Image URL upload successful: id={result.get('id')}")
        return result

    # ==========================================================
    # Upload Image from base64
    # ==========================================================
    @async_retry(max_retries=2, base_delay=2.0, retryable_exceptions=RETRYABLE)
    async def upload_image(
        self,
        image_base64: str,
        position: Optional[str] = None,
        emails: Optional[List[str]] = None,
        gender_required: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload image to Facebook Page with job vacancy caption.
        
        Args:
            image_base64: Base64 encoded image
            position: Job position title
            emails: List of contact emails
            gender_required: Gender requirement if any
            
        Returns:
            Response from Facebook API
        """
        url = f"{self.base_url}/{self.page_id}/photos"

        # Decode base64 image
        try:
            image_bytes = base64.b64decode(image_base64)
        except Exception as e:
            log.error(f"[ FACEBOOK ] Failed to decode base64: {e}")
            raise ValueError("Invalid base64 encoded image")

        # Validate image size (Facebook limit is 10MB for photos)
        image_size_mb = len(image_bytes) / (1024 * 1024)
        if image_size_mb > 10:
            raise ValueError(f"Image size ({image_size_mb:.2f}MB) exceeds 10MB limit")

        if len(image_bytes) < 1024:
            raise ValueError("Image too small, might be corrupted")

        log.debug(f"[ FACEBOOK ] Image size: {len(image_bytes)} bytes ({image_size_mb:.2f}MB)")

        formatted_caption = build_job_caption(
            position=position,
            emails=emails,
            gender_required=gender_required,
        )

        log.debug(f"[ FACEBOOK ] Caption length: {len(formatted_caption)} chars")

        client = await self._get_client()
        
        files = {"source": ("photo.jpg", BytesIO(image_bytes), "image/jpeg")}
        data = {
            "access_token": self.token,
            "message": formatted_caption,
        }

        log.debug(f"[ FACEBOOK ] Uploading to {url}")

        resp = await client.post(url, files=files, data=data)

        if resp.status_code != 200:
            log.error(f"[ FACEBOOK ] Upload failed: {resp.status_code} - {resp.text}")

        resp.raise_for_status()
        result = resp.json()

        log.info(
            f"[ FACEBOOK ] Upload successful: post_id={result.get('post_id') or result.get('id')}"
        )

        return result

    # ==========================================================
    # Test Connection
    # ==========================================================
    async def test_connection(self) -> bool:
        """Test Facebook API connection without uploading"""
        url = f"{self.base_url}/{self.page_id}"

        try:
            client = await self._get_client()
            resp = await client.get(
                url,
                params={
                    "access_token": self.token,
                    "fields": "id,name",
                },
            )
            resp.raise_for_status()

            data = resp.json()
            log.info(
                f"[ FACEBOOK ] Connection test successful: {data.get('name')} ({data.get('id')})"
            )
            return True

        except Exception as e:
            log.error(f"[ FACEBOOK ] Connection test failed: {e}")
            return False
