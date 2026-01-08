## services/instagram_client.py

import logging
import requests
import time

from typing import Optional, Dict, Any, List

log = logging.getLogger(__name__)

API_VERSION = "v24.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"


class InstagramUploader:
    def __init__(
        self,
        ig_page_id: str,
        access_token: str,
        base_url: str = BASE_URL,
        timeout: int = 30,
    ):
        self.ig_user_id = ig_page_id
        self.token = access_token
        self.base_url = base_url
        self.timeout = timeout
        
    # ==========================================================
    # Caption Builder (reuse logic dari Facebook)
    # ==========================================================
    def build_job_caption(
        self,
        position: Optional[str] = None,
        emails: Optional[List[str]] = None,
        gender_required: Optional[str] = None,
    ) -> str:
        lines = ["📢 INFO LOWONGAN KERJA", ""]

        if position:
            lines.append(f"🔹 Posisi: {position}")

        if gender_required:
            lines.append(f"🔹 Gender: {gender_required.upper()}")

        if emails:
            lines.append("")
            lines.append("📧 Kirim lamaran ke:")
            for email in emails:
                lines.append(f"• {email}")

        lines.append("")
        lines.append("#lowongankerja #loker #jobvacancy")

        return "\n".join(lines)


    # ==========================================================
    # Step 1: Create Media Container (IMAGE)
    # ==========================================================
    def _create_image_container(
        self,
        image_url: str,
        caption: str,
    ) -> str:
        url = f"{self.base_url}/{self.ig_user_id}/media"

        resp = requests.post(
            url,
            data={
                "image_url": image_url,
                "caption": caption,
                "access_token": self.token,
            },
            timeout=self.timeout,
        )

        if resp.status_code != 200:
            log.error(f"[ INSTAGRAM ] Media container failed: {resp.text}")
            resp.raise_for_status()

        return resp.json()["id"]

    # ==========================================================
    # Step 2: Publish Media
    # ==========================================================
    def _publish_media(self, creation_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/{self.ig_user_id}/media_publish"

        resp = requests.post(
            url,
            data={
                "creation_id": creation_id,
                "access_token": self.token,
            },
            timeout=self.timeout,
        )

        if resp.status_code != 200:
            log.error(f"[ INSTAGRAM ] Publish failed: {resp.text}")
            resp.raise_for_status()

        return resp.json()

    # ==========================================================
    # Public API: Upload Image
    # ==========================================================
    def upload_image(
        self,
        position: Optional[str] = None,
        emails: Optional[List[str]] = None,
        gender_required: Optional[str] = None,
        public_image_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload image to Instagram Feed

        NOTE:
        - Instagram requires PUBLIC image URL
        - image_base64 hanya dipakai jika kamu upload ke CDN sendiri dulu
        """

        caption = self.build_job_caption(
            position=position,
            emails=emails,
            gender_required=gender_required,
        )

        if not public_image_url:
            raise ValueError(
                "Instagram Graph API requires public image_url (CDN / S3 / Cloudflare)"
            )

        log.info("[ INSTAGRAM ] Creating media container")

        creation_id = self._create_image_container(
            image_url=public_image_url,
            caption=caption,
        )

        
        time.sleep(2)

        log.info("[ INSTAGRAM ] Publishing media")

        result = self._publish_media(creation_id)

        log.info(
            f"[ INSTAGRAM ] Upload success: media_id={result.get('id')}"
        )

        return result

    # ==========================================================
    # Public API: Upload Video (Reels)
    # ==========================================================
    def upload_video(
        self,
        video_url: str,
        caption: str,
    ) -> Dict[str, Any]:
        """
        Upload video (Reels)

        video_url MUST be publicly accessible
        """

        url = f"{self.base_url}/{self.ig_user_id}/media"

        resp = requests.post(
            url,
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "access_token": self.token,
            },
            timeout=600,
        )

        if resp.status_code != 200:
            log.error(f"[ INSTAGRAM ] Video container failed: {resp.text}")
            resp.raise_for_status()

        creation_id = resp.json()["id"]

        time.sleep(5)

        return self._publish_media(creation_id)

    # ==========================================================
    # Test Connection
    # ==========================================================
    def test_connection(self) -> bool:
        url = f"{self.base_url}/{self.ig_user_id}"

        try:
            resp = requests.get(
                url,
                params={
                    "fields": "id,username",
                    "access_token": self.token,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()

            data = resp.json()
            log.info(
                f"[ INSTAGRAM ] Connection OK: @{data.get('username')}"
            )
            return True

        except Exception as e:
            log.error(f"[ INSTAGRAM ] Connection failed: {e}")
            return False
