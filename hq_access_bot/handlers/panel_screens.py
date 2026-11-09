"""Screens of the admin panel, a single message whose text and buttons change in place."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from math import ceil

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from hq_access_bot import texts
from hq_access_bot.whitelist.models import Group, Whitelist

_GROUPS_PER_PAGE = 10
_GROUP_BUTTONS_PER_ROW = 2


class HomeButton(CallbackData, prefix="home"):
    pass


class StatusButton(CallbackData, prefix="status"):
    pass


class GroupsButton(CallbackData, prefix="groups"):
    page: int = 0


class GroupButton(CallbackData, prefix="group"):
    chat_key: str
    page: int = 0
    list_page: int = 0


@dataclass(frozen=True, slots=True)
class Screen:
    text: str
    keyboard: InlineKeyboardMarkup


def build_home_screen(whitelist: Whitelist) -> Screen:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(texts.BUTTON_GROUPS, GroupsButton()),
                _button(texts.BUTTON_STATUS, StatusButton()),
            ]
        ]
    )
    return Screen(texts.format_panel_home(whitelist), keyboard)


def build_status_text(whitelist: Whitelist, started_at_seconds: float) -> str:
    return texts.format_status_report(int(time.monotonic() - started_at_seconds), whitelist)


def build_status_screen(whitelist: Whitelist, started_at_seconds: float) -> Screen:
    return Screen(build_status_text(whitelist, started_at_seconds), _back_keyboard(HomeButton()))


def build_groups_screen(whitelist: Whitelist, page: int) -> Screen:
    entries = sorted(
        whitelist.groups.items(), key=lambda entry: (entry[1].project.lower(), entry[0])
    )
    if not entries:
        return Screen(texts.EMPTY_WHITELIST, _back_keyboard(HomeButton()))

    page_count = ceil(len(entries) / _GROUPS_PER_PAGE)
    page = min(page, page_count - 1)
    builder = InlineKeyboardBuilder()
    for chat_key, group in entries[page * _GROUPS_PER_PAGE : (page + 1) * _GROUPS_PER_PAGE]:
        data = GroupButton(chat_key=chat_key, list_page=page)
        builder.button(text=texts.format_group_button(group), callback_data=data)
    builder.adjust(_GROUP_BUTTONS_PER_ROW)
    builder.row(*_build_page_buttons(page, page_count, lambda p: GroupsButton(page=p)))
    builder.row(_button(texts.BUTTON_BACK, HomeButton()))
    return Screen(texts.format_groups_title(page, page_count), builder.as_markup())


def build_group_screen(chat_key: str, group: Group, page: int, list_page: int) -> Screen:
    pages = texts.format_group_card_pages(chat_key, group)
    page = min(page, len(pages) - 1)
    builder = InlineKeyboardBuilder()
    builder.row(
        *_build_page_buttons(
            page,
            len(pages),
            lambda p: GroupButton(chat_key=chat_key, page=p, list_page=list_page),
        )
    )
    builder.row(_button(texts.BUTTON_BACK, GroupsButton(page=list_page)))
    return Screen(pages[page], builder.as_markup())


def _build_page_buttons(
    page: int, page_count: int, open_page: Callable[[int], CallbackData]
) -> list[InlineKeyboardButton]:
    buttons = []
    if page > 0:
        buttons.append(_button(texts.BUTTON_PREVIOUS_PAGE, open_page(page - 1)))
    if page < page_count - 1:
        buttons.append(_button(texts.BUTTON_NEXT_PAGE, open_page(page + 1)))
    return buttons


def _back_keyboard(destination: CallbackData) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_button(texts.BUTTON_BACK, destination)]])


def _button(text: str, data: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data.pack())
