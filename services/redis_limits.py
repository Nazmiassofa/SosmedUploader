## services/redis_limits.py
"""
Per-platform daily post rate limiting via Redis.
"""

import datetime
import logging
from typing import Optional

from config.settings import config

log = logging.getLogger(__name__)

DAILY_LIMIT = config.REDIS_LIMIT


def _today_key(prefix: str) -> str:
    """Generate Redis key with today's date (UTC)"""
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    return f"{prefix}:{today}"


async def get_daily_post_count(redis, prefix: str) -> int:
    """Get today's post count for a specific platform prefix"""
    key = _today_key(prefix)

    value = await redis.get(key)
    if value is None:
        return 0

    try:
        return int(value)
    except ValueError:
        log.warning(f"[ REDIS LIMIT ] Invalid counter value for {key}")
        return 0


async def can_post_today(
    redis,
    prefix: str,
    limit: Optional[int] = None,
) -> bool:
    """
    Check whether posting is still allowed today for a given platform.
    
    Args:
        redis: Redis client
        prefix: Platform-specific prefix (e.g. 'instagram:daily_posts', 'facebook:daily_posts')
        limit: Override default limit for this platform
    """
    max_posts = limit if limit is not None else DAILY_LIMIT
    count = await get_daily_post_count(redis, prefix)
    return count < max_posts


async def increment_daily_post(redis, prefix: str) -> int:
    """
    Increment daily post counter and set TTL if first post today.

    Args:
        redis: Redis client
        prefix: Platform-specific prefix

    Returns:
        New counter value
    """
    key = _today_key(prefix)

    # Atomic increment
    count = await redis.incr(key)

    # If first increment today → set TTL 25 hours (buffer past midnight)
    if count == 1:
        await redis.expire(key, 60 * 60 * 25)
        log.info(f"[ REDIS LIMIT ] Initialized daily counter: {key}")

    log.debug(f"[ REDIS LIMIT ] {prefix} daily count: {count}/{DAILY_LIMIT}")

    return count
