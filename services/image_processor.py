## services/image_processor.py

import base64
import io
import logging
from PIL import Image
from typing import Tuple

log = logging.getLogger(__name__)


class ImageProcessor:
    """
    Helper class to process images for Instagram compatibility
    
    Instagram aspect ratio requirements:
    - Feed posts: 4:5 (portrait), 1.91:1 (landscape), 1:1 (square)
    - Recommended: 1080x1350 (4:5 portrait) or 1080x1080 (square)
    """
    
    # Instagram recommended dimensions
    INSTAGRAM_WIDTH = 1080
    INSTAGRAM_PORTRAIT_HEIGHT = 1350  # 4:5 ratio
    INSTAGRAM_SQUARE_HEIGHT = 1080    # 1:1 ratio
    
    # Aspect ratio limits
    MIN_ASPECT_RATIO = 0.8   # 4:5 (portrait)
    MAX_ASPECT_RATIO = 1.91  # landscape
    
    def __init__(self, target_mode: str = "portrait"):
        """
        Args:
            target_mode: 'portrait' (4:5), 'square' (1:1), or 'auto'
        """
        self.target_mode = target_mode
        
    def _calculate_target_size(
        self, 
        original_width: int, 
        original_height: int
    ) -> Tuple[int, int]:
        """
        Calculate target size based on mode and original aspect ratio
        
        Returns:
            (target_width, target_height)
        """
        original_ratio = original_width / original_height
        
        if self.target_mode == "square":
            return (self.INSTAGRAM_WIDTH, self.INSTAGRAM_SQUARE_HEIGHT)
        
        elif self.target_mode == "portrait":
            return (self.INSTAGRAM_WIDTH, self.INSTAGRAM_PORTRAIT_HEIGHT)
        
        else:  # auto mode
            # If already close to square, make it square
            if 0.95 <= original_ratio <= 1.05:
                return (self.INSTAGRAM_WIDTH, self.INSTAGRAM_SQUARE_HEIGHT)
            
            # If portrait-ish, make it 4:5
            elif original_ratio < 0.95:
                return (self.INSTAGRAM_WIDTH, self.INSTAGRAM_PORTRAIT_HEIGHT)
            
            # If landscape-ish but within limits
            elif original_ratio <= self.MAX_ASPECT_RATIO:
                target_height = int(self.INSTAGRAM_WIDTH / original_ratio)
                return (self.INSTAGRAM_WIDTH, target_height)
            
            # Too wide, crop to max landscape ratio
            else:
                target_height = int(self.INSTAGRAM_WIDTH / self.MAX_ASPECT_RATIO)
                return (self.INSTAGRAM_WIDTH, target_height)
    
    def _resize_and_pad(
        self, 
        image: Image.Image, 
        target_size: Tuple[int, int],
        bg_color: Tuple[int, int, int] = (255, 255, 255)
    ) -> Image.Image:
        """
        Resize image to fit target size and add padding if needed
        
        Args:
            image: PIL Image object
            target_size: (width, height)
            bg_color: Background color for padding (default white)
            
        Returns:
            Processed PIL Image
        """
        target_width, target_height = target_size
        
        # Convert to RGB if necessary
        if image.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', image.size, bg_color)
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Calculate scaling to fit within target size
        img_width, img_height = image.size
        scale = min(target_width / img_width, target_height / img_height)
        
        # Resize image
        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Create new image with target size and paste resized image
        new_image = Image.new('RGB', (target_width, target_height), bg_color)
        paste_x = (target_width - new_width) // 2
        paste_y = (target_height - new_height) // 2
        new_image.paste(image, (paste_x, paste_y))
        
        return new_image
    
    def _center_crop(
        self, 
        image: Image.Image, 
        target_size: Tuple[int, int]
    ) -> Image.Image:
        """
        Center crop image to target size
        
        Args:
            image: PIL Image object
            target_size: (width, height)
            
        Returns:
            Cropped PIL Image
        """
        target_width, target_height = target_size
        img_width, img_height = image.size
        
        # Calculate scaling to cover target size
        scale = max(target_width / img_width, target_height / img_height)
        
        # Resize image
        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Calculate crop box
        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        right = left + target_width
        bottom = top + target_height
        
        return image.crop((left, top, right, bottom))
    
    def process_base64_image(
        self,
        image_base64: str,
        crop_mode: str = "pad",
        quality: int = 95
    ) -> str:
        """
        Process base64 image for Instagram compatibility
        
        Args:
            image_base64: Base64 encoded image string
            crop_mode: 'pad' (add padding) or 'crop' (center crop)
            quality: JPEG quality (1-100)
            
        Returns:
            Base64 encoded processed image
        """
        try:
            # Decode base64
            image_bytes = base64.b64decode(image_base64)
            image = Image.open(io.BytesIO(image_bytes))
            
            original_size = image.size
            log.info(f"[ IMAGE PROCESSOR ] Original size: {original_size[0]}x{original_size[1]}")
            
            # Calculate target size
            target_size = self._calculate_target_size(image.size[0], image.size[1])
            log.info(f"[ IMAGE PROCESSOR ] Target size: {target_size[0]}x{target_size[1]}")
            
            # Process image based on crop mode
            if crop_mode == "crop":
                processed_image = self._center_crop(image, target_size)
            else:  # pad
                processed_image = self._resize_and_pad(image, target_size)
            
            # Convert back to base64
            buffer = io.BytesIO()
            processed_image.save(buffer, format='JPEG', quality=quality, optimize=True)
            processed_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            log.info(f"[ IMAGE PROCESSOR ] Processing complete: {crop_mode} mode")
            
            return processed_base64
            
        except Exception as e:
            log.error(f"[ IMAGE PROCESSOR ] Failed to process image: {e}", exc_info=True)
            raise
    
    def get_image_info(self, image_base64: str) -> dict:
        """
        Get image dimensions and aspect ratio info
        
        Returns:
            Dict with width, height, aspect_ratio, is_valid_for_instagram
        """
        try:
            image_bytes = base64.b64decode(image_base64)
            image = Image.open(io.BytesIO(image_bytes))
            
            width, height = image.size
            aspect_ratio = width / height
            
            is_valid = self.MIN_ASPECT_RATIO <= aspect_ratio <= self.MAX_ASPECT_RATIO
            
            return {
                "width": width,
                "height": height,
                "aspect_ratio": aspect_ratio,
                "is_valid_for_instagram": is_valid,
                "format": image.format,
                "mode": image.mode
            }
            
        except Exception as e:
            log.error(f"[ IMAGE PROCESSOR ] Failed to get image info: {e}")
            return {}