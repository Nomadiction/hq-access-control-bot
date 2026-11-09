"""What every inline button needs, wherever it is shown."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import Router
from aiogram.enums import ButtonStyle
from aiogram.exceptions import AiogramError, TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from hq_access_bot import texts

logger = logging.getLogger(__name__)

# Telegram refuses an edit that changes nothing, which is what a repeated press asks for.
_NOT_MODIFIED_ERROR = "message is not modified"

NextHandler = Callable[[CallbackQuery, dict[str, Any]], Awaitable[Any]]


def callback_button(
    text: str, data: CallbackData, style: ButtonStyle | None = None
) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data.pack(), style=style)


def single_row_keyboard(*buttons: InlineKeyboardButton) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(buttons)])


def confirmation_keyboard(confirm: CallbackData, cancel: CallbackData) -> InlineKeyboardMarkup:
    """Ask about an action that cannot be undone, which is what the red button stands for."""
    return single_row_keyboard(
        callback_button(texts.BUTTON_CONFIRM_DELETE, confirm, ButtonStyle.DANGER),
        callback_button(texts.BUTTON_CANCEL, cancel),
    )


def build_stale_button_router() -> Router:
    """Must come last: it answers every press that no other router took."""
    router = Router(name=__name__)
    router.callback_query.register(handle_stale_button)
    return router


async def handle_stale_button(callback: CallbackQuery) -> None:
    await acknowledge(callback, texts.STALE_BUTTON_NOTICE)


def is_not_modified(error: TelegramBadRequest) -> bool:
    return _NOT_MODIFIED_ERROR in error.message


async def edit_ignoring_no_change(edit: Awaitable[object]) -> None:
    try:
        await edit
    except TelegramBadRequest as error:
        if not is_not_modified(error):
            raise


async def acknowledge(callback: CallbackQuery, notice: str | None = None) -> None:
    """Stop the button's spinner. A press answered too late must still take effect."""
    try:
        await callback.answer(notice)
    except AiogramError as error:
        logger.warning("Button press was not acknowledged: %s", error)


async def stop_spinner_on_failure(
    handler: NextHandler, callback: CallbackQuery, data: dict[str, Any]
) -> Any:
    try:
        return await handler(callback, data)
    except Exception:
        await acknowledge(callback, texts.BUTTON_FAILURE_NOTICE)
        raise
