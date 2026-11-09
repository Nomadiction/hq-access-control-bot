"""Commands available to any user."""

import asyncio
import logging
from collections.abc import Iterator

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.types import LinkPreviewOptions, Message

from hq_access_bot import texts
from hq_access_bot.config import Settings
from hq_access_bot.handlers.telegram_mapping import build_person

logger = logging.getLogger(__name__)

# Telegram's limit for a single deleteMessages call.
_DELETE_BATCH_SIZE = 100

_PAUSE_BETWEEN_BATCHES_SECONDS = 0.3

# Deepest a single cleanup reaches, counted from the /clear message itself.
_MAX_CLEARED_MESSAGES = 1000

# Cleanups running at once across all chats: they share one rate limit with join requests.
_MAX_CONCURRENT_CLEANUPS = 3


def build_router() -> Router:
    router = Router(name=__name__)
    router.message.register(handle_welcome, Command("start", "help"))
    router.message.register(handle_chat_id, Command("id"))
    router.message.register(handle_own_id, Command("me"))
    router.message.register(
        _HistoryCleaner().handle_clear, Command("clear"), F.chat.type == ChatType.PRIVATE
    )
    return router


async def handle_welcome(message: Message, settings: Settings) -> None:
    is_admin = message.from_user.id in settings.admin_ids
    text = texts.ADMIN_WELCOME if is_admin else texts.format_user_welcome(settings.support_username)
    await message.answer(text, link_preview_options=LinkPreviewOptions(is_disabled=True))


async def handle_chat_id(message: Message) -> None:
    await message.answer(texts.format_chat_id_reply(message.chat.id))


async def handle_own_id(message: Message) -> None:
    await message.answer(texts.format_own_id_reply(build_person(message.from_user)))


class _HistoryCleaner:
    """Clears a chat's history, with one cleanup per chat at a time."""

    def __init__(self) -> None:
        self._busy_chat_ids: set[int] = set()

    async def handle_clear(self, message: Message, bot: Bot, settings: Settings) -> None:
        chat_id = message.chat.id
        if chat_id in self._busy_chat_ids or len(self._busy_chat_ids) >= _MAX_CONCURRENT_CLEANUPS:
            return
        self._busy_chat_ids.add(chat_id)
        try:
            await _delete_history(bot, chat_id, message.message_id)
        finally:
            self._busy_chat_ids.discard(chat_id)
        await handle_welcome(message, settings)


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
