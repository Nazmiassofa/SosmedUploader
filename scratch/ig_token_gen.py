import os
import httpx
import asyncio

from dotenv import load_dotenv


# Load .env from the project root
env_path = "/home/nazmiassofa/dev/SosmedUploader/.env"
load_dotenv(env_path)

USER_ACCESS_TOKEN = os.getenv("FB_USER_ACCESS_TOKEN")
APP_ID = os.getenv("FB_APP_ID")
APP_SECRET = os.getenv("FB_APP_SECRET")
API_VERSION = "v25.0"
FB_BASE_URL = f"https://graph.facebook.com/{API_VERSION}"
THREADS_BASE_URL = "https://graph.threads.net/v1.0"

async def get_long_lived_user_token(client, short_token):
    if not APP_ID or not APP_SECRET:
        print("Warning: FB_APP_ID or FB_APP_SECRET not found. Skipping long-lived exchange.")
        return short_token
    
    print("--- Exchanging for Long-lived User Access Token ---")
    try:
        response = await client.get(
            f"{FB_BASE_URL}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": APP_ID,
                "client_secret": APP_SECRET,
                "fb_exchange_token": short_token
            }
        )
        response.raise_for_status()
        data = response.json()
        long_token = data.get("access_token")
        print("Successfully obtained Long-lived User Token.")
        return long_token
    except Exception as e:
        print(f"Failed to exchange token: {e}")
        return short_token

async def run_generator():
    if not USER_ACCESS_TOKEN:
        print("Error: FB_USER_ACCESS_TOKEN not found in .env")
        return

    async with httpx.AsyncClient() as client:
        # Step 0: Exchange for Long-lived User Token
        long_lived_user_token = await get_long_lived_user_token(client, USER_ACCESS_TOKEN)

        # Step 1: Get Pages and their Page Access Tokens
        print(f"\n--- Fetching Facebook Pages ---")
        try:
            response = await client.get(
                f"{FB_BASE_URL}/me/accounts",
                params={"access_token": long_lived_user_token}
            )
            response.raise_for_status()
            pages_data = response.json().get("data", [])

            if not pages_data:
                print("No pages found for this user token.")
            else:
                for page in pages_data:
                    page_name = page.get("name")
                    page_id = page.get("id")
                    page_access_token = page.get("access_token")
                    
                    print(f"\nFound Page: {page_name} (ID: {page_id})")
                    
                    # Step 2: Get Instagram Business Account
                    ig_response = await client.get(
                        f"{FB_BASE_URL}/{page_id}",
                        params={
                            "fields": "instagram_business_account",
                            "access_token": page_access_token
                        }
                    )
                    ig_data = ig_response.json()
                    ig_business_account = ig_data.get("instagram_business_account")

                    # Step 3: Write to .env
                    print(f"--- Updating .env for {page_name} ---")
                    with open(env_path, "a") as f:
                        f.write(f'\n# Tokens for {page_name}\n')
                        f.write(f'FB_PAGE_ID = "{page_id}"\n')
                        f.write(f'FB_PAGE_ACCESS_TOKEN = "{page_access_token}"\n')
                        
                        if ig_business_account:
                            ig_id = ig_business_account.get("id")
                            f.write(f'IG_BUSINESS_ACCOUNT_ID = "{ig_id}"\n')
                            print(f"Linked Instagram Found: {ig_id}")
                        else:
                            print("No Instagram account linked to this page.")
                    
                    print(f"Successfully saved tokens for {page_name}")

        except Exception as e:
            print(f"Facebook/Instagram Error: {e}")

        # Step 4: Threads Check
        print(f"\n--- Fetching Threads Profile ---")
        try:
            # Threads requires its own graph domain
            threads_response = await client.get(
                f"{THREADS_BASE_URL}/me",
                params={
                    "fields": "id,username,threads_profile_picture_url,threads_biography",
                    "access_token": long_lived_user_token
                }
            )
            if threads_response.status_code == 200:
                threads_data = threads_response.json()
                threads_id = threads_data.get("id")
                threads_user = threads_data.get("username")
                print(f"Found Threads Account: {threads_user} (ID: {threads_id})")
                
                with open(env_path, "a") as f:
                    f.write(f'\n# Threads Config\n')
                    f.write(f'THREADS_USER_ID = "{threads_id}"\n')
                    f.write(f'THREADS_ACCESS_TOKEN = "{long_lived_user_token}"\n')
                print("Successfully saved Threads config to .env")
            else:
                print(f"Threads not found or permission missing. Status: {threads_response.status_code}")
                if threads_response.status_code == 400:
                    print("Hint: Make sure the token has 'threads_basic' permission.")

        except Exception as e:
            print(f"Threads Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_generator())
