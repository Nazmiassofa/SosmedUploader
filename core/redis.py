## core/redis.py

import logging
import asyncio
from typing import Optional
from redis.asyncio import Redis
from config.settings import config

log = logging.getLogger(__name__)

redis_client: Optional[Redis] = None
_health_check_task: Optional[asyncio.Task] = None


async def init_redis() -> Redis:
    """Initialize Redis async connection with health monitoring"""
    global redis_client, _health_check_task
    
    try:
        redis_client = Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            password=config.REDIS_PASSWORD,
            ssl=False,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=30,
        )
        
        # Test connection
        await redis_client.ping()
        log.info("[ REDIS ] Connection established")
        
        # Start health check loop
        _health_check_task = asyncio.create_task(
            _health_check_loop(),
            name="redis_health_check",
        )
        
        return redis_client
    
    except Exception as e:
        log.error(f"[ REDIS ] Failed to connect: {e}")
        raise


async def _health_check_loop(interval: int = 60) -> None:
    """Periodic health check with auto-reconnect"""
    global redis_client
    
    while True:
        try:
            await asyncio.sleep(interval)
            
            if redis_client is None:
                log.warning("[ REDIS ] Client is None, attempting reconnect...")
                await init_redis()
                continue
            
            await redis_client.ping()
            log.debug("[ REDIS ] Health check OK")
            
        except asyncio.CancelledError:
            log.info("[ REDIS ] Health check loop cancelled")
            return
        except Exception as e:
            log.error(f"[ REDIS ] Health check failed: {e}, attempting reconnect...")
            try:
                if redis_client:
                    await redis_client.aclose()
                    redis_client = None
                
                redis_client = Redis(
                    host=config.REDIS_HOST,
                    port=config.REDIS_PORT,
                    password=config.REDIS_PASSWORD,
                    ssl=False,
                    decode_responses=False,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    health_check_interval=30,
                )
                await redis_client.ping()
                log.info("[ REDIS ] Reconnected successfully")
            except Exception as reconnect_err:
                log.error(f"[ REDIS ] Reconnect failed: {reconnect_err}")


async def close_redis() -> None:
    """Close Redis connection gracefully"""
    global redis_client, _health_check_task
    
    # Cancel health check
    if _health_check_task and not _health_check_task.done():
        _health_check_task.cancel()
        try:
            await _health_check_task
        except asyncio.CancelledError:
            pass
        _health_check_task = None
    
    if redis_client:
        try:
            await redis_client.aclose()
            log.info("[ REDIS ] Connection closed")
        except Exception as e:
            log.error(f"[ REDIS ] Error closing connection: {e}")
        finally:
            redis_client = None


def get_redis() -> Optional[Redis]:
    """Get current Redis client instance"""
    return redis_client