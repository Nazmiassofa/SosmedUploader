## services/utils/retry.py

import asyncio
import logging
import functools
from typing import Callable, Type, Tuple

log = logging.getLogger(__name__)

# Default retryable exceptions for HTTP calls
DEFAULT_RETRYABLE = (
    ConnectionError,
    TimeoutError,
    OSError,
)


def async_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: Tuple[Type[BaseException], ...] = DEFAULT_RETRYABLE,
    on_retry_log_level: int = logging.WARNING,
) -> Callable:
    """
    Async retry decorator with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds (doubles each retry)
        max_delay: Maximum delay cap in seconds
        retryable_exceptions: Tuple of exception types to retry on
        on_retry_log_level: Log level for retry messages
        
    Usage:
        @async_retry(max_retries=3, base_delay=1.0)
        async def upload_image(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        log.log(
                            on_retry_log_level,
                            f"[ RETRY ] {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): "
                            f"{type(e).__name__}: {e}. Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        log.error(
                            f"[ RETRY ] {func.__name__} failed after {max_retries + 1} attempts: "
                            f"{type(e).__name__}: {e}"
                        )
            
            raise last_exception  # type: ignore[misc]
        
        return wrapper
    return decorator
