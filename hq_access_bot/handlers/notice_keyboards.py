"""Buttons on the notices sent to admins."""

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup

from hq_access_bot import texts
from hq_access_bot.handlers.buttons import (
    callback_button,
    confirmation_keyboard,
    single_row_keyboard,
)


class AddUnlistedButton(CallbackData, prefix="nadd"):
    chat_key: str
    user_id: int


class KickButton(CallbackData, prefix="nkick"):
    chat_key: str
    user_id: int


class AddDeclinedButton(CallbackData, prefix="nret"):
    chat_key: str
    user_id: int


class DecideRequestButton(CallbackData, prefix="ndec"):
    chat_key: str
    user_id: int
    approve: bool


class AskForgetGroupButton(CallbackData, prefix="nask"):
    chat_key: str


class ConfirmForgetGroupButton(CallbackData, prefix="nforget"):
    chat_key: str


class CancelForgetGroupButton(CallbackData, prefix="nkeep"):
    chat_key: str


def build_unlisted_member_keyboard(chat_key: str, user_id: int) -> InlineKeyboardMarkup:
    return single_row_keyboard(
        callback_button(
            texts.BUTTON_ADD_TO_LIST, AddUnlistedButton(chat_key=chat_key, user_id=user_id)
        ),
        callback_button(texts.BUTTON_KICK, KickButton(chat_key=chat_key, user_id=user_id)),
    )


def build_declined_request_keyboard(chat_key: str, user_id: int) -> InlineKeyboardMarkup:
    return single_row_keyboard(
        callback_button(
            texts.BUTTON_ADD_DECLINED, AddDeclinedButton(chat_key=chat_key, user_id=user_id)
        )
    )


def build_undecided_request_keyboard(chat_key: str, user_id: int) -> InlineKeyboardMarkup:
    return single_row_keyboard(
        callback_button(
            texts.BUTTON_APPROVE,
            DecideRequestButton(chat_key=chat_key, user_id=user_id, approve=True),
        ),
        callback_button(
            texts.BUTTON_DECLINE,
            DecideRequestButton(chat_key=chat_key, user_id=user_id, approve=False),
        ),
    )


def build_removed_bot_keyboard(chat_key: str) -> InlineKeyboardMarkup:
    return single_row_keyboard(
        callback_button(texts.BUTTON_FORGET_GROUP, AskForgetGroupButton(chat_key=chat_key))
    )


def build_forget_confirmation_keyboard(chat_key: str) -> InlineKeyboardMarkup:
    return confirmation_keyboard(
        ConfirmForgetGroupButton(chat_key=chat_key), CancelForgetGroupButton(chat_key=chat_key)
    )
