from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import httpx
from functools import wraps
from utils.logger import logger


def async_retry(max_attempts: int = 3, min_wait: float = 1, max_wait: float = 10):
    def decorator(func):
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException, ConnectionError)),
            reraise=True,
            before_sleep=lambda retry_state: logger.warning(
                f"Retry {retry_state.attempt_number}/{max_attempts} for {func.__name__}: {retry_state.outcome.exception()}"
            ),
        )
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        return wrapper

    return decorator
