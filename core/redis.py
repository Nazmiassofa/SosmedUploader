## core/redis.py

import logging
from redis.asyncio import Redis
from config.settings import config

log = logging.getLogger(__name__)

redis_client: Redis | None = None

async def init_redis() -> Redis:
    """Initialize Redis async connection"""
    global redis_client
    try:
        redis_client = Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            password=config.REDIS_PASSWORD,
            ssl=False,
            decode_responses=False,  # binary data
            socket_connect_timeout=5,
            socket_timeout=5
        )
        
        # Test connection
        await redis_client.ping()
        log.info("[ REDIS ] Connection established")
        return redis_client
    
    except Exception as e:
        log.error(f"[ REDIS ] Failed to connect: {e}")
        raise


async def close_redis():
    """Close Redis connection gracefully"""
    global redis_client
    if redis_client:
        try:
            await redis_client.aclose()
            log.info("[ REDIS ] Connection closed")
        except Exception as e:
            log.error(f"[ REDIS ] Error closing connection: {e}")
        finally:
            redis_client = None


def get_redis() -> Redis | None:
    """Get current Redis client instance"""
    return redis_client