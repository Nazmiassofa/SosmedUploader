"""
Image validation service
"""
import io
import base64
import logging
from typing import Optional
from PIL import Image

log = logging.getLogger(__name__)

class ImageValidator:
    """Validates image data before processing"""
    
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_DIMENSION = 5000
    
    def validate(self, image_base64: str) -> Optional[bytes]:
        """
        Validate base64 image and return decoded bytes if valid.
        
        Args:
            image_base64: Base64 encoded image string
            
        Returns:
            bytes: Decoded image bytes if valid
            None: If validation fails
        """
        # Remove base64 prefix if exists
        if "," in image_base64:
            image_base64 = image_base64.split(",", 1)[1]
        
        # Decode base64
        try:
            image_bytes = base64.b64decode(image_base64)
        except Exception as e:
            log.error(f"[ IMAGE ] Invalid base64 encoding: {e}")
            return None
        
        # Check file size
        if len(image_bytes) > self.MAX_IMAGE_SIZE:
            log.error(f"[ IMAGE ] Image too large: {len(image_bytes)} bytes (max: {self.MAX_IMAGE_SIZE})")
            return None
        
        # Validate image format and dimensions
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.verify()
            
            # Re-open for format/dimension check (verify() closes the file)
            img = Image.open(io.BytesIO(image_bytes))
            
            # Check dimensions
            width, height = img.size
            if width > self.MAX_DIMENSION or height > self.MAX_DIMENSION:
                log.error(f"[ IMAGE ] Image dimensions too large: {width}x{height} (max: {self.MAX_DIMENSION})")
                return None
            
            # Validate format
            if img.format not in ['JPEG', 'PNG', 'JPG']:
                log.error(f"[ IMAGE ] Unsupported format: {img.format}")
                return None
                            
        except Exception as e:
            log.error(f"[ IMAGE ] Invalid image data: {e}")
            return None
        
        return image_bytes
