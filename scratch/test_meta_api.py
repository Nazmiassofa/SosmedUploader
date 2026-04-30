import os
import httpx
from dotenv import load_dotenv

# Load .env from the project root
env_path = "/home/nazmiassofa/dev/SosmedUploader/.env"
load_dotenv(env_path)

# Tokens and IDs from .env
PAGE_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")
PAGE_ID = os.getenv("FB_PAGE_ID")
IG_ID = os.getenv("IG_BUSINESS_ACCOUNT_ID")

API_VERSION = "v25.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

async def test_meta_interaction():
    if not PAGE_TOKEN or not PAGE_ID or not IG_ID:
        print("Error: FB_PAGE_ACCESS_TOKEN, FB_PAGE_ID, or IG_BUSINESS_ACCOUNT_ID not found in .env")
        return

    async with httpx.AsyncClient() as client:
        print("=== TESTING META API INTERACTION ===\n")

        # 1. Test Facebook Page Interaction (GET Feed)
        print(f"--- 1. Testing Facebook Page (ID: {PAGE_ID}) ---")
        try:
            fb_response = await client.get(
                f"{BASE_URL}/{PAGE_ID}/feed",
                params={
                    "access_token": PAGE_TOKEN,
                    "limit": 3,
                    "fields": "message,created_time,id"
                }
            )
            fb_response.raise_for_status()
            fb_posts = fb_response.json().get("data", [])
            print(f"Status: Success!")
            print(f"Found {len(fb_posts)} latest posts on Facebook Page.")
            for post in fb_posts:
                msg = post.get("message", "[No Message]")[:50]
                print(f" - [{post.get('created_time')}] {msg}...")
        except Exception as e:
            print(f"Facebook Test Failed: {e}")

        print("\n" + "-"*40 + "\n")

        # 2. Test Instagram Business Interaction (GET Media)
        print(f"--- 2. Testing Instagram Business (ID: {IG_ID}) ---")
        try:
            ig_response = await client.get(
                f"{BASE_URL}/{IG_ID}/media",
                params={
                    "access_token": PAGE_TOKEN,
                    "limit": 3,
                    "fields": "caption,media_type,timestamp,permalink"
                }
            )
            ig_response.raise_for_status()
            ig_media = ig_response.json().get("data", [])
            print(f"Status: Success!")
            print(f"Found {len(ig_media)} latest media on Instagram.")
            for media in ig_media:
                caption = media.get("caption", "[No Caption]")[:50]
                print(f" - [{media.get('timestamp')}] {caption}...")
        except Exception as e:
            print(f"Instagram Test Failed: {e}")

        print("\n=== TEST COMPLETED ===")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_meta_interaction())
