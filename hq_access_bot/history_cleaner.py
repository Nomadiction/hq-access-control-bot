"""Deletion of a private chat's recent history."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterator

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

logger = logging.getLogger(__name__)

# Telegram's limit for a single deleteMessages call.
_DELETE_BATCH_SIZE = 100

_PAUSE_BETWEEN_BATCHES_SECONDS = 0.3

# Deepest a single cleanup reaches, counted from the newest message.
_MAX_CLEARED_MESSAGES = 1000

# Cleanups running at once across all chats: they share one rate limit with join requests.
_MAX_CONCURRENT_CLEANUPS = 3


class HistoryCleaner:
    """Clears chat histories, with one cleanup per chat at a time."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot
        self._busy_chat_ids: set[int] = set()

    async def clear(
        self, chat_id: int, read_newest_message_id: Callable[[], Awaitable[int]]
    ) -> bool:
        """Return whether the cleanup ran. The chat is reserved before anything is awaited."""
        if chat_id in self._busy_chat_ids or len(self._busy_chat_ids) >= _MAX_CONCURRENT_CLEANUPS:
            return False
        self._busy_chat_ids.add(chat_id)
        try:
            await _delete_history(self._bot, chat_id, await read_newest_message_id())
        finally:
            self._busy_chat_ids.discard(chat_id)
        return True


async def _delete_history(bot: Bot, chat_id: int, newest_message_id: int) -> None:
    """Delete recent messages, stopping at a rate limit shared with join request handling."""
    try:
        for batch in _split_into_batches(newest_message_id):
            await _delete_batch(bot, chat_id, batch)
            await asyncio.sleep(_PAUSE_BETWEEN_BATCHES_SECONDS)
    except TelegramRetryAfter as error:
        logger.warning("Cleanup of chat %s stopped by the rate limit: %s", chat_id, error)


def _split_into_batches(newest_message_id: int) -> Iterator[list[int]]:
    floor = max(newest_message_id - _MAX_CLEARED_MESSAGES, 0)
    for batch_top in range(newest_message_id, floor, -_DELETE_BATCH_SIZE):
        yield list(range(batch_top, max(batch_top - _DELETE_BATCH_SIZE, floor), -1))


async def _delete_batch(bot: Bot, chat_id: int, message_ids: list[int]) -> None:
    try:
        await bot.delete_messages(chat_id, message_ids)
    except TelegramRetryAfter:
        raise
    except TelegramAPIError:
        await _delete_one_by_one(bot, chat_id, message_ids)


async def _delete_one_by_one(bot: Bot, chat_id: int, message_ids: list[int]) -> None:
    for message_id in message_ids:
        # Some ids are empty or no longer accessible, which is expected during a cleanup.
        try:
            await bot.delete_message(chat_id, message_id)
        except TelegramRetryAfter:
            raise
        except TelegramAPIError:
            continue
