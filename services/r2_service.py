## services/r2_service.py

import base64
import boto3
import uuid
import datetime
import mimetypes
import logging
from typing import Optional

log = logging.getLogger(__name__)


class R2UploaderService:
    def __init__(
        self,
        account_id: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        public_base_url: str,
    ):
        self.bucket = bucket
        self.public_base = public_base_url.rstrip("/")

        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
        )

    def upload_base64_image(
        self,
        image_base64: str,
        folder: str = "jobs",
        ext: str = "jpg",
    ) -> str:
        """Upload a base64-encoded image to R2"""
        image_bytes = base64.b64decode(image_base64)
        return self.upload_image_bytes(image_bytes, folder=folder, ext=ext)

    def upload_image_bytes(
        self,
        image_bytes: bytes,
        folder: str = "jobs",
        ext: str = "jpg",
    ) -> str:
        """
        Upload raw image bytes to R2 — avoids redundant base64 round-trip.
        
        Args:
            image_bytes: Raw image bytes
            folder: R2 folder prefix
            ext: File extension
            
        Returns:
            Public URL of the uploaded image
        """
        today = datetime.datetime.now()
        filename = f"{uuid.uuid4().hex}.{ext}"
        key = f"{folder}/{today.year}/{today.month:02d}/{filename}"

        content_type = mimetypes.types_map.get(f".{ext}", "image/jpeg")

        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=image_bytes,
            ContentType=content_type,
            ACL="public-read",
        )

        url = f"{self.public_base}/{key}"
        log.debug(f"[ R2 ] Uploaded image: {url}")
        return url

    def upload_video(
        self,
        file_path: str,
        folder: str = "jobs/videos"
    ) -> str:
        """Upload a video file to R2"""
        filename = f"{uuid.uuid4().hex}.mp4"
        key = f"{folder}/{filename}"

        with open(file_path, "rb") as f:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=f,
                ContentType="video/mp4",
                ACL="public-read",
            )

        url = f"{self.public_base}/{key}"
        log.info(f"[ R2 ] Uploaded video: {url}")
        return url
    
    def clean_video(self, video_url: str) -> bool:
        """
        Delete video object from R2 using public URL.

        Args:
            video_url: Public video URL from R2

        Returns:
            True if deleted successfully
        """
        if not video_url.startswith(self.public_base):
            raise ValueError("Video URL does not belong to this R2 public base")

        # Extract object key from URL
        key = video_url.replace(self.public_base + "/", "", 1)

        if not key:
            raise ValueError("Invalid video URL, cannot extract object key")

        try:
            self.client.delete_object(
                Bucket=self.bucket,
                Key=key,
            )
            log.info(f"[ R2 ] Deleted: {key}")
            return True

        except Exception as e:
            raise RuntimeError(f"Failed to delete video from R2: {e}")
