import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, ClassVar
from dotenv import load_dotenv 

load_dotenv()

@dataclass(slots=True)
class Settings:
    
    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "127.0.0.1")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", "Nazmiassofa133")
    REDIS_CHANNEL: str = os.getenv("REDIS_CHANNEL", "job_vacancy_channel")
    REDIS_LIMIT: int = int(os.getenv("REDIS_LIMIT", "25"))
    
    # Meta Access
    PAGE_ACCESS_TOKEN : str = os.getenv("PAGE_ACCESS_TOKEN", "")
    INSTAGRAM_ID : str = os.getenv("INSTAGRAM_ID", "")
    INSTAGRAM_ACCESS_TOKEN : str = os.getenv("INSTAGRAM_ACCESS_TOKEN") or PAGE_ACCESS_TOKEN
    FACEBOOK_PAGE_ID : str = os.getenv("FACEBOOK_PAGE_ID", "")
    FACEBOOK_ACCESS_TOKEN : str = os.getenv("FACEBOOK_ACCESS_TOKEN") or PAGE_ACCESS_TOKEN
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "DEV")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Class variable 
    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parent.parent
    
    # R2 Storage
    R2_ACCOUNT_ID : str = os.getenv("R2_ACCOUNT_ID", "")
    R2_ACCESS_KEY : str = os.getenv("R2_ACCESS_KEY", "")
    R2_SECRET_KEY : str = os.getenv("R2_SECRET_KEY", "")
    R2_BASE_URL : str = os.getenv("R2_BASE_URL", "https://media.voisaretired.online")
    R2_BUCKET : str = os.getenv("R2_BUCKET", "media-job")
    
    

    def __post_init__(self) -> None:
        if self.ENVIRONMENT != "DEV":
            required = {
                "REDIS_HOST": self.REDIS_HOST,
                "REDIS_PASSWORD": self.REDIS_PASSWORD,
                "ENVIRONMENT": self.ENVIRONMENT,
                "FACEBOOK_PAGE_ID": self.FACEBOOK_PAGE_ID,
                "INSTAGRAM_ID": self.INSTAGRAM_ID,
                "FACEBOOK_ACCESS_TOKEN": self.FACEBOOK_ACCESS_TOKEN,
                "INSTAGRAM_ACCESS_TOKEN": self.INSTAGRAM_ACCESS_TOKEN,}
            missing = [k for k, v in required.items() if not v]
            if missing:
                raise RuntimeError(
                    f"Missing required environment variables: {', '.join(missing)}"
                )


config = Settings()
