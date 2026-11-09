"""Button presses in the admin panel."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import Router
from aiogram.exceptions import AiogramError, TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from hq_access_bot import texts
from hq_access_bot.config import Settings
from hq_access_bot.handlers.panel_screens import (
    GroupButton,
    GroupsButton,
    HomeButton,
    Screen,
    StatusButton,
    build_group_screen,
    build_groups_screen,
    build_home_screen,
    build_status_screen,
)
from hq_access_bot.handlers.telegram_mapping import is_admin_in_private_chat
from hq_access_bot.services import Services

logger = logging.getLogger(__name__)

# Telegram refuses an edit that changes nothing, which is what a repeated press asks for.
_NOT_MODIFIED_ERROR = "message is not modified"


def build_router() -> Router:
    """A press that no handler takes still needs an answer, or the button keeps spinning."""
    router = Router(name=__name__)
    router.include_routers(_build_panel_router(), _build_fallback_router())
    return router


def _build_panel_router() -> Router:
    router = Router(name="admin_panel_buttons")
    router.callback_query.filter(_is_admin_button_in_private_chat)
    router.callback_query.middleware(_stop_spinner_on_failure)
    router.callback_query.register(handle_open_home, HomeButton.filter())
    router.callback_query.register(handle_open_status, StatusButton.filter())
    router.callback_query.register(handle_open_groups, GroupsButton.filter())
    router.callback_query.register(handle_open_group, GroupButton.filter())
    return router


def _build_fallback_router() -> Router:
    router = Router(name="stale_buttons")
    router.callback_query.register(handle_stale_button)
    return router


async def handle_open_home(callback: CallbackQuery, services: Services) -> None:
    await _show(callback, build_home_screen(services.whitelist_store.read()))


async def handle_open_status(
    callback: CallbackQuery, services: Services, started_at_seconds: float
) -> None:
    whitelist = services.whitelist_store.read()
    await _show(callback, build_status_screen(whitelist, started_at_seconds))


async def handle_open_groups(
    callback: CallbackQuery, callback_data: GroupsButton, services: Services
) -> None:
    await _show(callback, build_groups_screen(services.whitelist_store.read(), callback_data.page))


async def handle_open_group(
    callback: CallbackQuery, callback_data: GroupButton, services: Services
) -> None:
    whitelist = services.whitelist_store.read()
    chat_key, list_page = callback_data.chat_key, callback_data.list_page
    group = whitelist.groups.get(chat_key)
    if group is None:
        await _show(callback, build_groups_screen(whitelist, list_page), texts.GROUP_GONE_NOTICE)
    else:
        await _show(callback, build_group_screen(chat_key, group, callback_data.page, list_page))


async def handle_stale_button(callback: CallbackQuery) -> None:
    await _acknowledge(callback, texts.STALE_BUTTON_NOTICE)


async def _is_admin_button_in_private_chat(callback: CallbackQuery, settings: Settings) -> bool:
    message = callback.message
    return isinstance(message, Message) and is_admin_in_private_chat(
        message.chat, callback.from_user, settings.admin_ids
    )


async def _stop_spinner_on_failure(
    handler: Callable[[CallbackQuery, dict[str, Any]], Awaitable[Any]],
    callback: CallbackQuery,
    data: dict[str, Any],
) -> Any:
    try:
        return await handler(callback, data)
    except Exception:
        await _acknowledge(callback, texts.PANEL_FAILURE_NOTICE)
        raise


async def _show(callback: CallbackQuery, screen: Screen, notice: str | None = None) -> None:
    await _acknowledge(callback, notice)
    try:
        await callback.message.edit_text(screen.text, reply_markup=screen.keyboard)
    except TelegramBadRequest as error:
        if _NOT_MODIFIED_ERROR not in error.message:
            raise


async def _acknowledge(callback: CallbackQuery, notice: str | None = None) -> None:
    """Stop the button's spinner. A press answered too late must still take effect."""
    try:
        await callback.answer(notice)
    except AiogramError as error:
        logger.warning("Button press was not acknowledged: %s", error)
