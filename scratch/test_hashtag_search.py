import asyncio
import logging
import httpx
import base64
from dotenv import load_dotenv

from config.settings import config
from services.r2_service import R2UploaderService

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

load_dotenv()

API_VERSION = "v25.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

async def get_hashtag_id(client: httpx.AsyncClient, hashtag_name: str) -> str:
    """Get Hashtag ID from hashtag name"""
    url = f"{BASE_URL}/ig_hashtag_search"
    params = {
        "user_id": config.INSTAGRAM_ID,
        "q": hashtag_name,
        "access_token": config.INSTAGRAM_ACCESS_TOKEN
    }
    
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    
    if not data.get("data"):
        raise ValueError(f"Hashtag #{hashtag_name} not found")
        
    hashtag_id = data["data"][0]["id"]
    log.info(f"Found Hashtag ID for #{hashtag_name}: {hashtag_id}")
    return hashtag_id

async def get_hashtag_recent_media(client: httpx.AsyncClient, hashtag_id: str) -> list:
    """Get recent media for a hashtag ID"""
    url = f"{BASE_URL}/{hashtag_id}/recent_media"
    params = {
        "user_id": config.INSTAGRAM_ID,
        "fields": "id,media_type,media_url,caption",
        "access_token": config.INSTAGRAM_ACCESS_TOKEN,
        "limit": 5
    }
    
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    return resp.json().get("data", [])

async def test_hashtag_workflow(hashtag_name: str):
    storage = R2UploaderService(
        account_id=config.R2_ACCOUNT_ID,
        access_key=config.R2_ACCESS_KEY,
        secret_key=config.R2_SECRET_KEY,
        public_base_url=config.R2_BASE_URL,
        bucket=config.R2_BUCKET
    )
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # 1. Search Hashtag ID
            log.info(f"Searching for hashtag: #{hashtag_name}...")
            hashtag_id = await get_hashtag_id(client, hashtag_name)
            
            # 2. Get Recent Media
            log.info(f"Fetching recent media for ID {hashtag_id}...")
            media_list = await get_hashtag_recent_media(client, hashtag_id)
            
            if not media_list:
                log.warning("No media found for this hashtag")
                return
            
            # 3. Pick one image media
            target_media = None
            for media in media_list:
                if media.get("media_type") == "IMAGE":
                    target_media = media
                    break
            
            if not target_media:
                log.warning("No image media found in recent posts")
                return
            
            media_url = target_media["media_url"]
            log.info(f"Found target image URL: {media_url}")
            
            # 4. Download image
            log.info("Downloading image...")
            resp = await client.get(media_url)
            resp.raise_for_status()
            image_bytes = resp.content
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            
            # 5. Upload to R2
            log.info("Uploading to R2...")
            # We use loop.run_in_executor because r2_service is currently synchronous
            loop = asyncio.get_running_loop()
            public_url = await loop.run_in_executor(
                None,
                storage.upload_base64_image,
                image_base64
            )
            log.info(f"Uploaded to R2: {public_url}")
            
            # 6. Delete from R2
            log.info("Deleting from R2...")
            success = await loop.run_in_executor(
                None,
                storage.clean_video, # This method handles deletion using public URL
                public_url
            )
            
            if success:
                log.info("Successfully deleted from R2")
            else:
                log.warning("Failed to delete from R2")
                
        except Exception as e:
            log.error(f"Workflow failed: {e}", exc_info=True)

if __name__ == "__main__":
    HASHTAG = "loker" # You can change this
    asyncio.run(test_hashtag_workflow(HASHTAG))
