import base64
import boto3
import uuid
import datetime
import mimetypes

from typing import Optional

class R2UploaderService:
    def __init__(
        self,
        account_id: str,
        access_key: str,
        secret_key: str,
        bucket: Optional[str] = "media-job",
        public_base_url: Optional[str] = "https://media.voisacommunity.online",
    ):
        self.bucket = bucket
        self.public_base = public_base_url.rstrip("/") if public_base_url else None

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
        image_bytes = base64.b64decode(image_base64)

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

        return f"{self.public_base}/{key}"
    
    
    def clean_video(self, video_url: str) -> bool:
        """
        Delete video object from R2 using public URL

        Args:
            video_url: Public video URL from R2

        Returns:
            True if deleted successfully, False otherwise
        """

        if not self.public_base:
            raise ValueError("public_base_url is not configured")

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

            return True

        except Exception as e:
            raise RuntimeError(f"Failed to delete video from R2: {e}")
