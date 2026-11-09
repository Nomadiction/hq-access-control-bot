"""Commands available to any user."""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import LinkPreviewOptions, Message

from hq_access_bot import texts
from hq_access_bot.config import Settings
from hq_access_bot.handlers.panel_screens import build_home_screen
from hq_access_bot.handlers.telegram_mapping import build_person, is_admin_in_private_chat
from hq_access_bot.services import Services
from hq_access_bot.whitelist.store import WhitelistCorruptedError


def build_router() -> Router:
    router = Router(name=__name__)
    router.message.register(handle_start, Command("start"))
    router.message.register(handle_help, Command("help"))
    router.message.register(handle_chat_id, Command("id"))
    router.message.register(handle_own_id, Command("me"))
    router.message.register(handle_clear, Command("clear"), F.chat.type == ChatType.PRIVATE)
    return router


async def handle_start(
    message: Message, settings: Settings, services: Services, state: FSMContext
) -> None:
    if not is_admin_in_private_chat(message.chat, message.from_user, settings.admin_ids):
        await handle_help(message, settings)
        return
    # A new panel replaces the one that may be waiting for typed input.
    await state.clear()
    try:
        whitelist = services.whitelist_store.read()
    except WhitelistCorruptedError:
        # The failure alert is throttled, and the admin still needs an answer every time.
        await handle_help(message, settings)
        raise
    screen = build_home_screen(whitelist)
    await message.answer(screen.text, reply_markup=screen.keyboard)


async def handle_help(message: Message, settings: Settings) -> None:
    is_admin = message.from_user.id in settings.admin_ids
    text = texts.ADMIN_WELCOME if is_admin else texts.format_user_welcome(settings.support_username)
    await message.answer(text, link_preview_options=LinkPreviewOptions(is_disabled=True))


async def handle_chat_id(message: Message) -> None:
    await message.answer(texts.format_chat_id_reply(message.chat.id))


async def handle_own_id(message: Message) -> None:
    await message.answer(texts.format_own_id_reply(build_person(message.from_user)))


async def handle_clear(
    message: Message, settings: Settings, services: Services, state: FSMContext
) -> None:
    async def read_newest_message_id() -> int:
        return message.message_id

    if await services.history_cleaner.clear(message.chat.id, read_newest_message_id):
        await handle_start(message, settings, services, state)
