## services/facebook_client.py

import base64
import logging
import requests
import os

from typing import Optional, Dict, Any, List
from io import BytesIO

log = logging.getLogger(__name__)

API_VERSION = "v24.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

class FacebookUploader:
    def __init__(
        self,
        page_id: str,
        page_access_token: str,
        base_url: str = BASE_URL,
        timeout: int = 30
    ):  
        self.page_id = page_id
        self.token = page_access_token
        self.base_url = base_url
        self.timeout = timeout

    def build_job_caption(self,
                          position: Optional[str] = None,
                          emails: Optional[List[str]] = None,
                          gender_required: Optional[str] = None,
                          ) -> str:
        """
        Build job vacancy caption with structured information
        """
        lines = ["📢 INFO LOWONGAN KERJA"]
        lines.append("")
        
        has_details = False
        
        if position:
            lines.append(f"🔹 Posisi: {position}")
            has_details = True
        
        if gender_required:
            gender_display = gender_required.upper()
            lines.append(f"🔹 Gender: {gender_display}")
            has_details = True
        
        if emails and len(emails) > 0:
            lines.append("")
            lines.append("📧 Kirim lamaran ke:")
            for email in emails:
                lines.append(f"   • {email}")
            has_details = True
        
        # Add separator if we have details
        if has_details:
            lines.append("")
        
        return "\n".join(lines)
    
    def upload_video_from_url(
        self,
        video_url: str,
        description: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload video to Facebook Page using remote URL

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

        try:
            resp = requests.post(
                url,
                data=data,
                timeout=600,  # remote fetch bisa lama
            )

            if resp.status_code != 200:
                log.error(
                    f"[ FACEBOOK ] Video URL upload failed: "
                    f"{resp.status_code} - {resp.text}"
                )

            resp.raise_for_status()
            result = resp.json()

            log.info(
                f"[ FACEBOOK ] Video URL upload successful: video_id={result.get('id')}"
            )

            return result

        except requests.exceptions.Timeout:
            log.error("[ FACEBOOK ] Video URL upload timeout")
            raise

        except requests.exceptions.RequestException as e:
            log.error(f"[ FACEBOOK ] Video URL upload request failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                log.error(f"[ FACEBOOK ] Response: {e.response.text}")
            raise

    def upload_image(self,
                    image_base64: str,
                    position: Optional[str] = None,
                    emails: Optional[List[str]] = None,
                    gender_required: Optional[str] = None) -> Dict[str, Any]:
        """
        Upload image to Facebook Page with job vacancy caption
        
        Args:
            image_base64: Base64 encoded image
            caption: Original caption text
            position: Job position title
            emails: List of contact emails
            gender_required: Gender requirement if any
            
        Returns:
            Response from Facebook API
        """
        url = f"{self.base_url}/{self.page_id}/photos"

        try:
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
            
            # Validate minimum size (at least 1KB to be a valid image)
            if len(image_bytes) < 1024:
                raise ValueError("Image too small, might be corrupted")

            log.debug(f"[ FACEBOOK ] Image size: {len(image_bytes)} bytes ({image_size_mb:.2f}MB)")

            # Build structured caption
            formatted_caption = self.build_job_caption(
                position=position,
                emails=emails,
                gender_required=gender_required,
            )

            log.debug(f"[ FACEBOOK ] Caption length: {len(formatted_caption)} chars")

            # Method 1: Try with BytesIO (most compatible)
            files = {
                "source": ("photo.jpg", BytesIO(image_bytes), "image/jpeg")
            }

            data = {
                "access_token": self.token,
                "message": formatted_caption,
            }

            log.debug(f"[ FACEBOOK ] Uploading to {url}")

            resp = requests.post(
                url,
                files=files,
                data=data,
                timeout=self.timeout,
            )
            
            # If BytesIO fails, try with raw bytes
            if resp.status_code == 400 and "Invalid parameter" in resp.text:
                log.warning("[ FACEBOOK ] BytesIO upload failed, trying raw bytes...")
                
                files = {
                    "source": image_bytes
                }
                
                resp = requests.post(
                    url,
                    files=files,
                    data=data,
                    timeout=self.timeout,
                )
            
            # Log response for debugging
            if resp.status_code != 200:
                log.error(
                    f"[ FACEBOOK ] Upload failed: {resp.status_code} - {resp.text}"
                )
            
            resp.raise_for_status()
            result = resp.json()
            
            log.info(
                f"[ FACEBOOK ] Upload successful: post_id={result.get('post_id') or result.get('id')}"
            )
    
            return result

        except ValueError as e:
            log.error(f"[ FACEBOOK ] Validation error: {e}")
            raise
        except requests.exceptions.Timeout:
            log.error("[ FACEBOOK ] Request timeout")
            raise
        except requests.exceptions.RequestException as e:
            log.error(f"[ FACEBOOK ] Request failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                log.error(f"[ FACEBOOK ] Response: {e.response.text}")
            raise
        except Exception as e:
            log.error(f"[ FACEBOOK ] Unexpected error: {e}")
            raise

    def test_connection(self) -> bool:
        """
        Test Facebook API connection without uploading
        
        Returns:
            True if connection is successful
        """
        url = f"{self.base_url}/{self.page_id}"
        
        try:
            resp = requests.get(
                url,
                params={
                    "access_token": self.token,
                    "fields": "id,name",
                },
                timeout=self.timeout,
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