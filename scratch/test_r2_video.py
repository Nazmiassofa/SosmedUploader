
import os
import sys
import boto3
from dotenv import load_dotenv
from PIL import Image
import numpy as np

# Add current directory to path to import services
sys.path.append(os.getcwd())

from services.media.video_generator import VideoGenerator
from config.settings import config

def test_generate_video_from_r2():
    # Load environment variables
    load_dotenv()
    
    # Credentials
    account_id = os.getenv("R2_ACCOUNT_ID")
    access_key = os.getenv("R2_ACCESS_KEY")
    secret_key = os.getenv("R2_SECRET_KEY")
    bucket_name = os.getenv("R2_BUCKET", "media-job")
    
    if not all([account_id, access_key, secret_key]):
        print("❌ Error: Missing R2 credentials in .env")
        return

    # Initialize R2 client
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )

    print(f"🔍 Fetching last 10 images from bucket: {bucket_name}...")
    
    try:
        # List objects in the bucket
        response = s3.list_objects_v2(Bucket=bucket_name)
        
        if 'Contents' not in response:
            print("❌ No objects found in bucket")
            return
            
        # Filter for images and sort by last modified
        objects = response['Contents']
        # Filter: check if it's in a 'jobs' folder and has image extension
        image_objects = [
            obj for obj in objects 
            if any(obj['Key'].lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png'])
        ]
        
        # Sort by LastModified descending
        image_objects.sort(key=lambda x: x['LastModified'], reverse=True)
        
        # Take the last 10
        target_objects = image_objects[:10]
        
        if not target_objects:
            print("❌ No image objects found")
            return
            
        print(f"✅ Found {len(target_objects)} images. Downloading...")
        
        # Create temp directory for images
        temp_dir = "scratch/temp_images"
        os.makedirs(temp_dir, exist_ok=True)
        
        local_image_paths = []
        for i, obj in enumerate(target_objects):
            key = obj['Key']
            local_path = os.path.join(temp_dir, f"img_{i}.jpg")
            print(f"   Downloading {key} -> {local_path}")
            s3.download_file(bucket_name, key, local_path)
            local_image_paths.append(local_path)
            
        # Initialize VideoGenerator
        # Using default resolution (720, 1280) and 3 seconds per image
        gen = VideoGenerator(
            resolution=(720, 1280),
            duration_per_image=3.0,
            fps=24
        )
        
        output_video = "scratch/test_r2_output.mp4"
        print(f"🎬 Generating video: {output_video}...")
        
        success = gen.generate(local_image_paths, output_video)
        
        if success:
            print(f"✨ SUCCESS! Video generated at: {output_video}")
            print(f"   File size: {os.path.getsize(output_video) / (1024*1024):.2f} MB")
        else:
            print("❌ Video generation failed")
            
        # Optional: cleanup images but keep video
        # for p in local_image_paths: os.remove(p)
        # os.rmdir(temp_dir)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_generate_video_from_r2()
