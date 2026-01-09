import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, ClassVar
from dotenv import load_dotenv 

load_dotenv()

@dataclass(slots=True)
class Settings:
    
    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")
    REDIS_CHANNEL: str = os.getenv("REDIS_CHANNEL", "")
    REDIS_LIMIT: int = int(os.getenv("REDIS_LIMIT", "25"))
    
    # Meta Access
    FACEBOOK_PAGE_ID : str = os.getenv("FACEBOOK_PAGE_ID", "")

    INSTAGRAM_ID : str = os.getenv("INSTAGRAM_ID", "")    
    ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "")
    

    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "DEV")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Class variable 
    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parent.parent
    
    # R2 Storage
    R2_ACCOUNT_ID : str = os.getenv("R2_ACCOUNT_ID", "")
    R2_ACCESS_KEY : str = os.getenv("R2_ACCESS_KEY", "")
    R2_SECRET_KEY : str = os.getenv("R2_SECRET_KEY", "")
    
    

    def __post_init__(self) -> None:
        if self.ENVIRONMENT != "DEV":
            required = {
                "REDIS_HOST": self.REDIS_HOST,
                "REDIS_PASSWORD": self.REDIS_PASSWORD,
            }
            missing = [k for k, v in required.items() if not v]
            if missing:
                raise RuntimeError(
                    f"Missing required environment variables: {', '.join(missing)}"
                )


config = Settings()
