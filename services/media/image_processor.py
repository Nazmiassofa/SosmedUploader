## services/media/image_processor.py
"""
Consolidated image processing — handles validation, Instagram resizing,
and video-frame preparation in one module.
"""

import io
import base64
import logging
from typing import Optional, Tuple, Dict, Any

from PIL import Image, ImageOps

log = logging.getLogger(__name__)


class ImageProcessor:
    """
    Unified image processor for:
    - Validation (format, size, dimensions)
    - Instagram aspect-ratio compliance
    - Efficient bytes-in / bytes-out processing
    
    Instagram aspect ratio requirements:
    - Feed posts: 4:5 (portrait), 1.91:1 (landscape), 1:1 (square)
    - Recommended: 1080x1350 (4:5 portrait) or 1080x1080 (square)
    """

    # Instagram recommended dimensions
    INSTAGRAM_WIDTH = 1080
    INSTAGRAM_PORTRAIT_HEIGHT = 1350  # 4:5 ratio
    INSTAGRAM_SQUARE_HEIGHT = 1080   # 1:1 ratio

    # Aspect ratio limits
    MIN_ASPECT_RATIO = 0.8   # 4:5 (portrait)
    MAX_ASPECT_RATIO = 1.91  # landscape

    # Validation limits
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_DIMENSION = 5000

    def __init__(self, target_mode: str = "portrait"):
        """
        Args:
            target_mode: 'portrait' (4:5), 'square' (1:1), or 'auto'
        """
        self.target_mode = target_mode

    # ==========================================================
    # Validation
    # ==========================================================
    def validate_base64(self, image_base64: str) -> Optional[bytes]:
        """
        Validate base64 image and return decoded bytes if valid.
        
        Returns:
            bytes if valid, None if validation fails
        """
        # Remove base64 prefix if exists
        if "," in image_base64:
            image_base64 = image_base64.split(",", 1)[1]

        try:
            image_bytes = base64.b64decode(image_base64)
        except Exception as e:
            log.error(f"[ IMAGE ] Invalid base64 encoding: {e}")
            return None

        if len(image_bytes) > self.MAX_IMAGE_SIZE:
            log.error(f"[ IMAGE ] Image too large: {len(image_bytes)} bytes")
            return None

        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.verify()

            # Re-open for dimension check (verify() closes the file)
            img = Image.open(io.BytesIO(image_bytes))

            width, height = img.size
            if width > self.MAX_DIMENSION or height > self.MAX_DIMENSION:
                log.error(f"[ IMAGE ] Dimensions too large: {width}x{height}")
                return None

            if img.format not in ["JPEG", "PNG", "JPG"]:
                log.error(f"[ IMAGE ] Unsupported format: {img.format}")
                return None

        except Exception as e:
            log.error(f"[ IMAGE ] Invalid image data: {e}")
            return None

        return image_bytes

    # ==========================================================
    # Instagram Processing — bytes in, bytes out
    # ==========================================================
    def process_image_bytes(
        self,
        image_bytes: bytes,
        crop_mode: str = "pad",
        quality: int = 95,
    ) -> bytes:
        """
        Process raw image bytes for Instagram compatibility.
        Returns processed bytes directly — no base64 round-trip.
        
        Args:
            image_bytes: Raw image bytes
            crop_mode: 'pad' (add padding) or 'crop' (center crop)
            quality: JPEG quality (1-100)
            
        Returns:
            Processed image as bytes
        """
        with Image.open(io.BytesIO(image_bytes)) as image:
            image = ImageOps.exif_transpose(image)

            original_size = image.size
            log.info(f"[ IMAGE ] Original: {original_size[0]}x{original_size[1]}")

            target_size = self._calculate_target_size(image.size[0], image.size[1])
            log.info(f"[ IMAGE ] Target: {target_size[0]}x{target_size[1]}")

            if crop_mode == "crop":
                processed = self._center_crop(image, target_size)
            else:
                processed = self._resize_and_pad(image, target_size)

            buffer = io.BytesIO()
            processed.save(buffer, format="JPEG", quality=quality, optimize=True)
            result = buffer.getvalue()

            # Explicit cleanup
            del processed
        
        return result

    def process_base64_image(
        self,
        image_base64: str,
        crop_mode: str = "pad",
        quality: int = 95,
    ) -> str:
        """
        Process base64 image for Instagram compatibility.
        Legacy method — prefer process_image_bytes() for new code.
        """
        image_bytes = base64.b64decode(image_base64)
        processed_bytes = self.process_image_bytes(image_bytes, crop_mode, quality)
        return base64.b64encode(processed_bytes).decode("utf-8")

    # ==========================================================
    # Image Info
    # ==========================================================
    def get_image_info(self, image_base64: str) -> Dict[str, Any]:
        """Get image dimensions and aspect ratio info"""
        try:
            image_bytes = base64.b64decode(image_base64)
            return self.get_image_info_from_bytes(image_bytes)
        except Exception as e:
            log.error(f"[ IMAGE ] Failed to get image info: {e}")
            return {}

    def get_image_info_from_bytes(self, image_bytes: bytes) -> Dict[str, Any]:
        """Get image dimensions and aspect ratio info from raw bytes"""
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image = ImageOps.exif_transpose(image)

                width, height = image.size
                aspect_ratio = width / height

                return {
                    "width": width,
                    "height": height,
                    "aspect_ratio": aspect_ratio,
                    "is_valid_for_instagram": self.MIN_ASPECT_RATIO <= aspect_ratio <= self.MAX_ASPECT_RATIO,
                    "format": image.format,
                    "mode": image.mode,
                }
        except Exception as e:
            log.error(f"[ IMAGE ] Failed to get image info: {e}")
            return {}

    # ==========================================================
    # Internal helpers
    # ==========================================================
    def _calculate_target_size(
        self,
        original_width: int,
        original_height: int,
    ) -> Tuple[int, int]:
        original_ratio = original_width / original_height

        if self.target_mode == "square":
            return (self.INSTAGRAM_WIDTH, self.INSTAGRAM_SQUARE_HEIGHT)
        elif self.target_mode == "portrait":
            return (self.INSTAGRAM_WIDTH, self.INSTAGRAM_PORTRAIT_HEIGHT)
        else:  # auto
            if 0.95 <= original_ratio <= 1.05:
                return (self.INSTAGRAM_WIDTH, self.INSTAGRAM_SQUARE_HEIGHT)
            elif original_ratio < 0.95:
                return (self.INSTAGRAM_WIDTH, self.INSTAGRAM_PORTRAIT_HEIGHT)
            elif original_ratio <= self.MAX_ASPECT_RATIO:
                target_height = int(self.INSTAGRAM_WIDTH / original_ratio)
                return (self.INSTAGRAM_WIDTH, target_height)
            else:
                target_height = int(self.INSTAGRAM_WIDTH / self.MAX_ASPECT_RATIO)
                return (self.INSTAGRAM_WIDTH, target_height)

    def _resize_and_pad(
        self,
        image: Image.Image,
        target_size: Tuple[int, int],
        bg_color: Tuple[int, int, int] = (255, 255, 255),
    ) -> Image.Image:
        target_width, target_height = target_size

        if image.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", image.size, bg_color)
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(
                image,
                mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None,
            )
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        img_width, img_height = image.size
        scale = min(target_width / img_width, target_height / img_height)

        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        new_image = Image.new("RGB", (target_width, target_height), bg_color)
        paste_x = (target_width - new_width) // 2
        paste_y = (target_height - new_height) // 2
        new_image.paste(image, (paste_x, paste_y))

        return new_image

    def _center_crop(
        self,
        image: Image.Image,
        target_size: Tuple[int, int],
    ) -> Image.Image:
        target_width, target_height = target_size
        img_width, img_height = image.size

        scale = max(target_width / img_width, target_height / img_height)

        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        right = left + target_width
        bottom = top + target_height

        return image.crop((left, top, right, bottom))
