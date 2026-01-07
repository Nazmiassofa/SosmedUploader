import datetime
import logging
from typing import Optional

from config.settings import config

log = logging.getLogger(__name__)

DAILY_LIMIT = config.REDIS_LIMIT

def _today_key(prefix: str) -> str:
    """
    Generate Redis key with today's date (UTC)
    """
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    return f"{prefix}:{today}"


async def get_daily_post_count(redis, prefix: str) -> int:
    """
    Get today's post count
    """
    key = _today_key(prefix)

    value = await redis.get(key)
    if value is None:
        return 0

    try:
        return int(value)
    except ValueError:
        log.warning(f"[ REDIS LIMIT ] Invalid counter value for {key}")
        return 0


async def can_post_today(redis, prefix: str) -> bool:
    """
    Check whether posting is still allowed today
    """
    count = await get_daily_post_count(redis, prefix)
    return count < DAILY_LIMIT


async def increment_daily_post(redis, prefix: str) -> int:
    """
    Increment daily post counter and set TTL if first post today

    Returns:
        New counter value
    """
    key = _today_key(prefix)

    # Atomic increment
    count = await redis.incr(key)

    # If first increment today → set TTL 24 hours
    if count == 1:
        await redis.expire(key, 60 * 60 * 24)
        log.info(f"[ REDIS LIMIT ] Initialized daily counter: {key}")

    log.debug(f"[ REDIS LIMIT ] Daily post count: {count}/{DAILY_LIMIT}")

    return count
