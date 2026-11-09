"""Screens of the admin panel, a single message whose text and buttons change in place."""

import hashlib
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import ceil

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from hq_access_bot import texts
from hq_access_bot.handlers.buttons import (
    callback_button,
    confirmation_keyboard,
    single_row_keyboard,
)
from hq_access_bot.whitelist.models import Group, Member, Whitelist

_GROUPS_PER_PAGE = 10
_GROUP_BUTTONS_PER_ROW = 2
_MEMBERS_PER_REMOVE_PAGE = 10
_MEMBER_TAG_LENGTH = 12


class HomeButton(CallbackData, prefix="home"):
    pass


class StatusButton(CallbackData, prefix="status"):
    pass


class ClearChatButton(CallbackData, prefix="clear"):
    pass


class GroupsButton(CallbackData, prefix="groups"):
    page: int = 0


class SyncButton(CallbackData, prefix="sync"):
    page: int = 0


class GroupButton(CallbackData, prefix="group"):
    chat_key: str
    page: int = 0
    list_page: int = 0


class AddMembersButton(CallbackData, prefix="add"):
    chat_key: str
    list_page: int = 0


class RemoveListButton(CallbackData, prefix="rmlist"):
    chat_key: str
    page: int = 0
    list_page: int = 0


class RemoveMemberButton(CallbackData, prefix="rm"):
    chat_key: str
    member_tag: str
    page: int = 0
    list_page: int = 0


class AskDeleteGroupButton(CallbackData, prefix="askdel"):
    chat_key: str
    list_page: int = 0


class ConfirmDeleteGroupButton(CallbackData, prefix="del"):
    chat_key: str
    list_page: int = 0


@dataclass(frozen=True, slots=True)
class Screen:
    text: str
    keyboard: InlineKeyboardMarkup


def find_member_by_tag(group: Group, tag: str) -> Member | None:
    return next((member for member in group.members if _member_tag(member) == tag), None)


def build_home_screen(whitelist: Whitelist) -> Screen:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                callback_button(texts.BUTTON_GROUPS, GroupsButton()),
                callback_button(texts.BUTTON_STATUS, StatusButton()),
            ],
            [callback_button(texts.BUTTON_CLEAR_CHAT, ClearChatButton())],
        ]
    )
    return Screen(texts.format_panel_home(whitelist), keyboard)


def build_status_text(whitelist: Whitelist, started_at_seconds: float) -> str:
    return texts.format_status_report(int(time.monotonic() - started_at_seconds), whitelist)


def build_status_screen(whitelist: Whitelist, started_at_seconds: float) -> Screen:
    return Screen(build_status_text(whitelist, started_at_seconds), _back_keyboard(HomeButton()))


def build_groups_screen(whitelist: Whitelist, page: int, notice: str | None = None) -> Screen:
    entries = sorted(
        whitelist.groups.items(), key=lambda entry: (entry[1].project.lower(), entry[0])
    )
    if not entries:
        return Screen(texts.EMPTY_WHITELIST, _back_keyboard(HomeButton()))

    visible, page, page_count = _select_page(entries, _GROUPS_PER_PAGE, page)
    builder = InlineKeyboardBuilder()
    for chat_key, group in visible:
        data = GroupButton(chat_key=chat_key, list_page=page)
        builder.button(text=texts.format_group_button(group), callback_data=data)
    builder.adjust(_GROUP_BUTTONS_PER_ROW)
    builder.row(*_build_page_buttons(page, page_count, lambda p: GroupsButton(page=p)))
    builder.row(callback_button(texts.BUTTON_SYNC, SyncButton(page=page)))
    builder.row(callback_button(texts.BUTTON_BACK, HomeButton()))
    return Screen(texts.format_groups_title(page, page_count, notice), builder.as_markup())


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
    builder.row(
        callback_button(texts.BUTTON_ADD, AddMembersButton(chat_key=chat_key, list_page=list_page)),
        callback_button(
            texts.BUTTON_REMOVE, RemoveListButton(chat_key=chat_key, list_page=list_page)
        ),
    )
    builder.row(
        callback_button(
            texts.BUTTON_DELETE_GROUP, AskDeleteGroupButton(chat_key=chat_key, list_page=list_page)
        )
    )
    builder.row(callback_button(texts.BUTTON_BACK, GroupsButton(page=list_page)))
    return Screen(pages[page], builder.as_markup())


def build_add_prompt_screen(
    chat_key: str, group: Group, list_page: int, error: str | None = None
) -> Screen:
    cancel = GroupButton(chat_key=chat_key, list_page=list_page)
    keyboard = single_row_keyboard(callback_button(texts.BUTTON_CANCEL, cancel))
    return Screen(texts.format_add_prompt(group, error), keyboard)


def build_add_result_screen(chat_key: str, report: str, list_page: int) -> Screen:
    keyboard = single_row_keyboard(
        callback_button(
            texts.BUTTON_ADD_MORE, AddMembersButton(chat_key=chat_key, list_page=list_page)
        ),
        callback_button(
            texts.BUTTON_BACK_TO_GROUP, GroupButton(chat_key=chat_key, list_page=list_page)
        ),
    )
    return Screen(report, keyboard)


def build_remove_screen(chat_key: str, group: Group, page: int, list_page: int) -> Screen:
    visible, page, page_count = _select_page(group.members, _MEMBERS_PER_REMOVE_PAGE, page)
    builder = InlineKeyboardBuilder()
    for member in visible:
        data = RemoveMemberButton(
            chat_key=chat_key, member_tag=_member_tag(member), page=page, list_page=list_page
        )
        builder.row(callback_button(texts.format_member_button(member), data))
    builder.row(
        *_build_page_buttons(
            page,
            page_count,
            lambda p: RemoveListButton(chat_key=chat_key, page=p, list_page=list_page),
        )
    )
    builder.row(
        callback_button(texts.BUTTON_BACK, GroupButton(chat_key=chat_key, list_page=list_page))
    )
    return Screen(texts.format_remove_title(group, page, page_count), builder.as_markup())


def build_delete_confirmation_screen(chat_key: str, group: Group, list_page: int) -> Screen:
    keyboard = confirmation_keyboard(
        ConfirmDeleteGroupButton(chat_key=chat_key, list_page=list_page),
        GroupButton(chat_key=chat_key, list_page=list_page),
    )
    return Screen(texts.format_delete_confirmation(group), keyboard)


def _select_page[T](items: Sequence[T], per_page: int, page: int) -> tuple[Sequence[T], int, int]:
    """Return a page of items, its number, cut to the last page, and the number of pages."""
    page_count = max(ceil(len(items) / per_page), 1)
    page = min(page, page_count - 1)
    return items[page * per_page : (page + 1) * per_page], page, page_count


def _member_tag(member: Member) -> str:
    """Name a member in a button. A hand-edited username may not fit the button's data."""
    digest = hashlib.sha256(str(member.identity).encode()).hexdigest()
    return digest[:_MEMBER_TAG_LENGTH]


def _build_page_buttons(
    page: int, page_count: int, open_page: Callable[[int], CallbackData]
) -> list[InlineKeyboardButton]:
    buttons = []
    if page > 0:
        buttons.append(callback_button(texts.BUTTON_PREVIOUS_PAGE, open_page(page - 1)))
    if page < page_count - 1:
        buttons.append(callback_button(texts.BUTTON_NEXT_PAGE, open_page(page + 1)))
    return buttons


def _back_keyboard(destination: CallbackData) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[callback_button(texts.BUTTON_BACK, destination)]])
