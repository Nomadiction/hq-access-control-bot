"""Commands available to any user."""

import asyncio
from collections.abc import Iterator

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import LinkPreviewOptions, Message

from hq_access_bot import texts
from hq_access_bot.config import Settings
from hq_access_bot.handlers.telegram_mapping import build_person

# Telegram's limit for a single deleteMessages call.
_DELETE_BATCH_SIZE = 100

_PAUSE_BETWEEN_BATCHES_SECONDS = 0.3


def build_router() -> Router:
    router = Router(name=__name__)
    router.message.register(handle_welcome, Command("start", "help"))
    router.message.register(handle_chat_id, Command("id"))
    router.message.register(handle_own_id, Command("me"))
    router.message.register(handle_clear, Command("clear"), F.chat.type == ChatType.PRIVATE)
    return router


async def handle_welcome(message: Message, settings: Settings) -> None:
    is_admin = message.from_user.id in settings.admin_ids
    text = texts.ADMIN_WELCOME if is_admin else texts.format_user_welcome(settings.support_username)
    await message.answer(text, link_preview_options=LinkPreviewOptions(is_disabled=True))


async def handle_chat_id(message: Message) -> None:
    await message.answer(texts.format_chat_id_reply(message.chat.id))


async def handle_own_id(message: Message) -> None:
    await message.answer(texts.format_own_id_reply(build_person(message.from_user)))


async def handle_clear(message: Message, bot: Bot, settings: Settings) -> None:
    for batch in _split_into_batches(message.message_id):
        await _delete_batch(bot, message.chat.id, batch)
        await asyncio.sleep(_PAUSE_BETWEEN_BATCHES_SECONDS)
    await handle_welcome(message, settings)


def _split_into_batches(newest_message_id: int) -> Iterator[list[int]]:
    for batch_top in range(newest_message_id, 0, -_DELETE_BATCH_SIZE):
        yield list(range(batch_top, max(batch_top - _DELETE_BATCH_SIZE, 0), -1))


async def _delete_batch(bot: Bot, chat_id: int, message_ids: list[int]) -> None:
    try:
        await bot.delete_messages(chat_id, message_ids)
    except TelegramAPIError:
        await _delete_one_by_one(bot, chat_id, message_ids)


async def _delete_one_by_one(bot: Bot, chat_id: int, message_ids: list[int]) -> None:
    for message_id in message_ids:
        # Some ids are empty or no longer accessible, which is expected during a cleanup.
        try:
            await bot.delete_message(chat_id, message_id)
        except TelegramAPIError:
            continue
