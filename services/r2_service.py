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
