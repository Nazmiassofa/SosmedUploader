"""
Video generation service using MoviePy - Low Memory Version
"""
import logging
from typing import List, Optional, Tuple
from PIL import Image
import os
import random

# Pillow >=10 compatibility for MoviePy
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS # type: ignore

from moviepy.editor import (
    ImageClip,
    concatenate_videoclips,
    CompositeVideoClip,
    ColorClip,
    AudioFileClip
)

log = logging.getLogger(__name__)

SOUNDTRACK_DIR = "data/templates/sound"

class VideoGenerator:
    """Generates slideshow videos from images - Low Memory Version"""
    
    def __init__(
        self,
        resolution: Tuple[int, int] = (720, 1280),
        duration_per_image: float = 3.0,
        fps: int = 24,
        background_color: Tuple[int, int, int] = (255, 255, 255)  # White background
    ):
        self.resolution = resolution
        self.duration_per_image = duration_per_image
        self.fps = fps
        self.background_color = background_color
        
        
    def _pick_random_audio(self) -> Optional[str]:
        """
        Pick one random audio file from SOUNDTRACK_DIR
        Returns path to audio file or None
        """
        if not os.path.isdir(SOUNDTRACK_DIR):
            log.warning(f"[ VIDEO ] Sound directory not found: {SOUNDTRACK_DIR}")
            return None

        # Common audio extensions MoviePy can handle
        audio_exts = (".mp3", ".wav", ".aac", ".m4a", ".ogg")

        audio_files = [
            os.path.join(SOUNDTRACK_DIR, f)
            for f in os.listdir(SOUNDTRACK_DIR)
            if f.lower().endswith(audio_exts)
        ]

        if not audio_files:
            log.warning("[ VIDEO ] No audio files found in sound directory")
            return None

        # If only one file, use it directly
        if len(audio_files) == 1:
            return audio_files[0]

        # Pick random if more than one
        return random.choice(audio_files)
    
    def generate(self, image_paths: List[str], output_path: str) -> bool:
        """
        Generate slideshow video from images
        
        Args:
            image_paths: List of paths to image files
            output_path: Path where video should be saved
            
        Returns:
            bool: True if successful, False otherwise
        """
        clips = []
        final_clip = None
        audio_clip = None
        
        try:
            for img_path in image_paths:
                clip = self._create_composite_clip(img_path)
                if clip:
                    clips.append(clip)
            
            if not clips:
                log.error("[ VIDEO ] No clips created")
                return False
            
            # Concatenate all clips
            final_clip = concatenate_videoclips(clips, method="compose")
            
            # Add audio if soundtrack exists
            try:
                audio_path = self._pick_random_audio()
                if audio_path:                    
                    audio_clip = AudioFileClip(audio_path)
                    
                    # Loop audio to match video duration
                    video_duration = final_clip.duration
                    if audio_clip.duration < video_duration:
                        loops = int(video_duration / audio_clip.duration) + 1
                        audio_clip = audio_clip.audio_loop(n=loops) # type: ignore
                    
                    # Trim audio to exact video duration
                    audio_clip = audio_clip.subclip(0, video_duration)
                    
                    # Set audio to video
                    final_clip = final_clip.set_audio(audio_clip)
                    log.info(f"[ VIDEO ] Audio added from {audio_path}")
                else:
                    log.warning(f"[ VIDEO ] No audio file provided - [ skip audio ]")
            except Exception as e:
                log.warning(f"[ VIDEO ] Failed to add audio: {e}")
            
            # Write video file
            final_clip.write_videofile(
                output_path,
                fps=self.fps,
                codec="libx264",
                audio_codec="aac",
                threads=1,
                preset="ultrafast",
                logger=None  # Suppress MoviePy's verbose output
            )
            
            log.info(f"[ VIDEO ] Video generated: {output_path}")
            return True
            
        except Exception as e:
            log.error(f"[ VIDEO ] Failed to generate video: {e}", exc_info=True)
            return False
            
        finally:
            # Clean up clips
            for clip in clips:
                try:
                    clip.close()
                except Exception as e:
                    log.warning(f"[ VIDEO ] Failed to close clip: {e}")
            
            if audio_clip:
                try:
                    audio_clip.close()
                except Exception as e:
                    log.warning(f"[ VIDEO ] Failed to close audio clip: {e}")
            
            if final_clip:
                try:
                    final_clip.close()
                except Exception as e:
                    log.warning(f"[ VIDEO ] Failed to close final clip: {e}")
    
    def _create_composite_clip(self, img_path: str) -> Optional[CompositeVideoClip]:
        """
        Create composite clip with solid color background and centered foreground
        
        Args:
            img_path: Path to image file
            
        Returns:
            CompositeVideoClip or None if failed
        """
        try:
            # Create solid color background (no processing needed - very light on memory)
            bg_clip = ColorClip(
                size=self.resolution,
                color=self.background_color,
                duration=self.duration_per_image
            )
            
            # Create foreground (maintains aspect ratio)
            fg_clip = self._create_foreground_clip(img_path)
            
            # Composite both layers
            composite = CompositeVideoClip(
                [
                    bg_clip,
                    fg_clip.set_position("center")
                ],
                size=self.resolution
            )
            
            return composite
            
        except Exception as e:
            log.error(f"[ VIDEO ] Failed to create clip for {img_path}: {e}")
            return None
    
    def _create_foreground_clip(self, img_path: str) -> ImageClip:
        """
        Create foreground clip that fits within resolution without stretching
        
        Args:
            img_path: Path to image file
            
        Returns:
            ImageClip: Properly sized foreground clip
        """
        clip = ImageClip(img_path)
        
        # Get original dimensions
        original_width, original_height = clip.size
        target_width, target_height = self.resolution
        
        # Calculate scaling factor to fit within target resolution
        width_ratio = target_width / original_width
        height_ratio = target_height / original_height
        scale_factor = min(width_ratio, height_ratio)
        
        # Calculate new dimensions
        new_width = int(original_width * scale_factor)
        new_height = int(original_height * scale_factor)
        
        # Resize maintaining aspect ratio using tuple (width, height)
        resized_clip = clip.resize((new_width, new_height)) # type: ignore
        
        return resized_clip.set_duration(self.duration_per_image)
