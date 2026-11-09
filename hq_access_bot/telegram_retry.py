"""Retries for Telegram calls whose loss cannot be recovered later."""

import asyncio
from collections.abc import Awaitable, Callable

from aiogram.exceptions import (
    ClientDecodeError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)

# Failures that say nothing about the request itself, so sending it again can succeed.
TRANSIENT_FAILURES = (TelegramNetworkError, TelegramServerError, ClientDecodeError)

_MAX_ATTEMPTS = 5
_NETWORK_RETRY_PAUSE_SECONDS = 2.0
# Longest pause requested by Telegram that is still worth holding a request open for.
_MAX_RATE_LIMIT_WAIT_SECONDS = 60


async def call_with_retry[T](call: Callable[[], Awaitable[T]]) -> T:
    """Repeat a call after a rate limit or a transient failure.

    Raises:
        AiogramError: the call was rejected, or the attempts ran out.
    """
    for _ in range(_MAX_ATTEMPTS - 1):
        try:
            return await call()
        except TelegramRetryAfter as error:
            if error.retry_after > _MAX_RATE_LIMIT_WAIT_SECONDS:
                raise
            await asyncio.sleep(error.retry_after)
        except TRANSIENT_FAILURES:
            await asyncio.sleep(_NETWORK_RETRY_PAUSE_SECONDS)
    return await call()
