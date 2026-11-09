"""The admin panel: button presses and the text typed in answer to them."""

import logging
from collections.abc import Callable
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import AiogramError, TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from hq_access_bot import texts
from hq_access_bot.handlers.access_list_changes import (
    ADD_MEMBERS,
    REMOVE_MEMBERS,
    apply_member_operation,
    delete_group,
    sync_with_telegram,
)
from hq_access_bot.handlers.buttons import (
    NextHandler,
    acknowledge,
    edit_ignoring_no_change,
    is_not_modified,
    stop_spinner_on_failure,
)
from hq_access_bot.handlers.command_args import parse_members
from hq_access_bot.handlers.panel_screens import (
    AddMembersButton,
    AskDeleteGroupButton,
    ClearChatButton,
    ConfirmDeleteGroupButton,
    GroupButton,
    GroupsButton,
    HomeButton,
    RemoveListButton,
    RemoveMemberButton,
    Screen,
    StatusButton,
    SyncButton,
    build_add_prompt_screen,
    build_add_result_screen,
    build_delete_confirmation_screen,
    build_group_screen,
    build_groups_screen,
    build_home_screen,
    build_remove_screen,
    build_status_screen,
    find_member_by_tag,
)
from hq_access_bot.handlers.telegram_mapping import (
    is_admin_button_in_private_chat,
    is_admin_message_in_private_chat,
)
from hq_access_bot.services import Services
from hq_access_bot.whitelist.identity import MemberRef
from hq_access_bot.whitelist.models import Group

logger = logging.getLogger(__name__)


class _PendingInput(StatesGroup):
    members_to_add = State()


class _SyncButtonHandler:
    """Runs one sync at a time: a double tap would poll every member twice."""

    def __init__(self) -> None:
        self._is_running = False

    async def handle(
        self,
        callback: CallbackQuery,
        callback_data: SyncButton,
        bot: Bot,
        services: Services,
        state: FSMContext,
    ) -> None:
        if self._is_running:
            await acknowledge(callback, texts.SYNC_BUSY_NOTICE)
            return
        self._is_running = True
        await acknowledge(callback, texts.SYNC_STARTED_NOTICE)
        try:
            whitelist = await sync_with_telegram(bot, services)
        finally:
            self._is_running = False
        # By now the admin may have opened a screen that is waiting for typed input.
        if await state.get_state() is None:
            screen = build_groups_screen(whitelist, callback_data.page, texts.SYNC_DONE_NOTE)
            await _edit(callback, screen)


def build_router() -> Router:
    router = Router(name=__name__)
    router.callback_query.filter(is_admin_button_in_private_chat)
    router.callback_query.middleware(stop_spinner_on_failure)
    router.callback_query.middleware(_forget_pending_input)
    router.callback_query.register(handle_open_home, HomeButton.filter())
    router.callback_query.register(handle_open_status, StatusButton.filter())
    router.callback_query.register(handle_clear_chat, ClearChatButton.filter())
    router.callback_query.register(handle_open_groups, GroupsButton.filter())
    router.callback_query.register(_SyncButtonHandler().handle, SyncButton.filter())
    router.callback_query.register(handle_open_group, GroupButton.filter())
    router.callback_query.register(handle_ask_members, AddMembersButton.filter())
    router.callback_query.register(handle_open_remove_list, RemoveListButton.filter())
    router.callback_query.register(handle_remove_member, RemoveMemberButton.filter())
    router.callback_query.register(handle_ask_delete_group, AskDeleteGroupButton.filter())
    router.callback_query.register(handle_confirm_delete_group, ConfirmDeleteGroupButton.filter())

    router.message.filter(is_admin_message_in_private_chat)
    is_plain_text = (F.text, ~F.text.startswith("/"))
    router.message.register(handle_members_input, _PendingInput.members_to_add, *is_plain_text)
    router.message.register(handle_unexpected_text, StateFilter(None), *is_plain_text)
    return router


async def handle_open_home(callback: CallbackQuery, services: Services) -> None:
    await _show(callback, build_home_screen(services.whitelist_store.read()))


async def handle_open_status(
    callback: CallbackQuery, services: Services, started_at_seconds: float
) -> None:
    whitelist = services.whitelist_store.read()
    await _show(callback, build_status_screen(whitelist, started_at_seconds))


async def handle_clear_chat(callback: CallbackQuery, bot: Bot, services: Services) -> None:
    """Clean from a fresh message: the pressed panel may be older than the rest of the chat."""
    chat_id = callback.message.chat.id

    async def send_marker() -> int:
        await acknowledge(callback)
        marker = await bot.send_message(chat_id, texts.CLEARING_NOTICE)
        return marker.message_id

    if await services.history_cleaner.clear(chat_id, send_marker):
        screen = build_home_screen(services.whitelist_store.read())
        await bot.send_message(chat_id, screen.text, reply_markup=screen.keyboard)
    else:
        await acknowledge(callback, texts.CLEANUP_BUSY_NOTICE)


async def handle_open_groups(
    callback: CallbackQuery, callback_data: GroupsButton, services: Services
) -> None:
    await _show(callback, build_groups_screen(services.whitelist_store.read(), callback_data.page))


async def handle_open_group(
    callback: CallbackQuery, callback_data: GroupButton, services: Services
) -> None:
    chat_key, list_page = callback_data.chat_key, callback_data.list_page
    await _show_for_group(
        callback,
        services,
        chat_key,
        list_page,
        lambda group: build_group_screen(chat_key, group, callback_data.page, list_page),
    )


async def handle_ask_members(
    callback: CallbackQuery,
    callback_data: AddMembersButton,
    services: Services,
    state: FSMContext,
) -> None:
    chat_key, list_page = callback_data.chat_key, callback_data.list_page
    is_prompt_shown = await _show_for_group(
        callback,
        services,
        chat_key,
        list_page,
        lambda group: build_add_prompt_screen(chat_key, group, list_page),
    )
    if is_prompt_shown:
        await state.update_data(
            chat_key=chat_key, list_page=list_page, panel_message_id=callback.message.message_id
        )
        await state.set_state(_PendingInput.members_to_add)


async def handle_open_remove_list(
    callback: CallbackQuery, callback_data: RemoveListButton, services: Services
) -> None:
    chat_key, list_page = callback_data.chat_key, callback_data.list_page
    await _show_for_group(
        callback,
        services,
        chat_key,
        list_page,
        lambda group: build_remove_screen(chat_key, group, callback_data.page, list_page),
    )


async def handle_remove_member(
    callback: CallbackQuery, callback_data: RemoveMemberButton, services: Services
) -> None:
    chat_key, list_page = callback_data.chat_key, callback_data.list_page
    group = services.whitelist_store.read().groups.get(chat_key)
    member = find_member_by_tag(group, callback_data.member_tag) if group else None
    notice = texts.MEMBER_GONE_NOTICE
    if member is not None:
        await apply_member_operation(REMOVE_MEMBERS, chat_key, [member.ref], services)
        notice = texts.format_member_removed_notice(member.ref.label)
    await _show_for_group(
        callback,
        services,
        chat_key,
        list_page,
        lambda current: build_remove_screen(chat_key, current, callback_data.page, list_page),
        notice,
    )


async def handle_ask_delete_group(
    callback: CallbackQuery, callback_data: AskDeleteGroupButton, services: Services
) -> None:
    chat_key, list_page = callback_data.chat_key, callback_data.list_page
    await _show_for_group(
        callback,
        services,
        chat_key,
        list_page,
        lambda group: build_delete_confirmation_screen(chat_key, group, list_page),
    )


async def handle_confirm_delete_group(
    callback: CallbackQuery, callback_data: ConfirmDeleteGroupButton, services: Services
) -> None:
    group = await delete_group(callback_data.chat_key, services)
    notice = texts.GROUP_DELETED_NOTICE if group else texts.GROUP_GONE_NOTICE
    screen = build_groups_screen(services.whitelist_store.read(), callback_data.list_page)
    await _show(callback, screen, notice)


async def handle_members_input(
    message: Message, state: FSMContext, bot: Bot, services: Services
) -> None:
    pending = await state.get_data()
    if "chat_key" not in pending:
        return  # A press or an earlier message has just ended this wait.
    try:
        screen = await _take_typed_members(message.text, pending, state, services)
    except Exception:
        await _resume_waiting(state, pending)
        await services.notifier.send_direct_message(message.chat.id, texts.BUTTON_FAILURE_NOTICE)
        raise
    await _delete_quietly(message)
    await _edit_panel(message, bot, pending["panel_message_id"], screen)


async def handle_unexpected_text(message: Message) -> None:
    await message.answer(texts.NOT_WAITING_FOR_INPUT)


async def _take_typed_members(
    text: str, pending: dict[str, Any], state: FSMContext, services: Services
) -> Screen:
    """Add what was typed. The wait ends before the first real pause, so it is taken once."""
    chat_key, list_page = pending["chat_key"], pending["list_page"]
    refs, invalid = parse_members(text)
    error = _describe_input_problem(refs, invalid)
    group = services.whitelist_store.read().groups.get(chat_key)
    if group is not None and error is not None:
        return build_add_prompt_screen(chat_key, group, list_page, error)

    await state.clear()
    report = await apply_member_operation(ADD_MEMBERS, chat_key, refs, services)
    if report is None:
        whitelist = services.whitelist_store.read()
        return build_groups_screen(whitelist, list_page, texts.GROUP_GONE_NOTICE)
    return build_add_result_screen(chat_key, report, list_page)


async def _resume_waiting(state: FSMContext, pending: dict[str, Any]) -> None:
    await state.update_data(pending)
    await state.set_state(_PendingInput.members_to_add)


def _describe_input_problem(refs: list[MemberRef], invalid: list[str]) -> str | None:
    if invalid:
        return texts.format_invalid_usernames(invalid)
    return None if refs else texts.MEMBERS_INPUT_EMPTY


async def _forget_pending_input(
    handler: NextHandler, callback: CallbackQuery, data: dict[str, Any]
) -> Any:
    """Any press leaves the screen that was asking for typed input."""
    await data["state"].clear()
    return await handler(callback, data)


async def _show_for_group(
    callback: CallbackQuery,
    services: Services,
    chat_key: str,
    list_page: int,
    build: Callable[[Group], Screen],
    notice: str | None = None,
) -> bool:
    """Show a screen about a group, or the list if the group is no longer there.

    Returns whether the screen about the group was shown.
    """
    whitelist = services.whitelist_store.read()
    group = whitelist.groups.get(chat_key)
    if group is None:
        await _show(callback, build_groups_screen(whitelist, list_page), texts.GROUP_GONE_NOTICE)
        return False
    await _show(callback, build(group), notice)
    return True


async def _show(callback: CallbackQuery, screen: Screen, notice: str | None = None) -> None:
    await acknowledge(callback, notice)
    await _edit(callback, screen)


async def _edit(callback: CallbackQuery, screen: Screen) -> None:
    await edit_ignoring_no_change(
        callback.message.edit_text(screen.text, reply_markup=screen.keyboard)
    )


async def _edit_panel(message: Message, bot: Bot, panel_message_id: int, screen: Screen) -> None:
    """Show the outcome of typed input; the admin may have deleted the panel meanwhile."""
    try:
        await bot.edit_message_text(
            text=screen.text,
            chat_id=message.chat.id,
            message_id=panel_message_id,
            reply_markup=screen.keyboard,
        )
    except TelegramBadRequest as error:
        if not is_not_modified(error):
            await message.answer(screen.text, reply_markup=screen.keyboard)


async def _delete_quietly(message: Message) -> None:
    try:
        await message.delete()
    except AiogramError as error:
        logger.warning("Could not delete the admin's message: %s", error)
