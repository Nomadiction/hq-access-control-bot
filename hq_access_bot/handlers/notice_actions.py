"""Button presses on the notices sent to admins.

A press closes the notice: the buttons go and the outcome is written under its text. Every
admin has a copy, so each action also has to make sense when another admin got there first.
"""

import logging
from typing import Any

from aiogram import Bot, Router
from aiogram.exceptions import AiogramError
from aiogram.types import CallbackQuery, ChatMember, InlineKeyboardMarkup

from hq_access_bot import texts
from hq_access_bot.handlers.access_list_changes import (
    ADD_MEMBERS,
    ForgetOutcome,
    apply_member_operation,
    confirm_member_in_chat,
    forget_inactive_group,
    look_up_chat_member,
)
from hq_access_bot.handlers.buttons import (
    NextHandler,
    acknowledge,
    edit_ignoring_no_change,
    stop_spinner_on_failure,
)
from hq_access_bot.handlers.notice_keyboards import (
    AddDeclinedButton,
    AddUnlistedButton,
    AskForgetGroupButton,
    CancelForgetGroupButton,
    ConfirmForgetGroupButton,
    DecideRequestButton,
    KickButton,
    build_forget_confirmation_keyboard,
    build_removed_bot_keyboard,
)
from hq_access_bot.handlers.telegram_mapping import (
    build_person,
    is_admin_button_in_private_chat,
    is_request_already_resolved,
)
from hq_access_bot.services import Services
from hq_access_bot.telegram_retry import call_with_retry
from hq_access_bot.whitelist.identity import MemberRef
from hq_access_bot.whitelist.store import WhitelistCorruptedError

logger = logging.getLogger(__name__)

_FORGET_RESULTS = {
    ForgetOutcome.FORGOTTEN: texts.GROUP_FORGOTTEN_RESULT,
    ForgetOutcome.ALREADY_GONE: texts.GROUP_GONE_NOTICE,
    ForgetOutcome.BOT_RETURNED: texts.BOT_RETURNED_RESULT,
}


class _OnePressPerNotice:
    """Keeps a double tap from running an action twice."""

    def __init__(self) -> None:
        self._busy_notices: set[tuple[int, int]] = set()

    async def __call__(
        self, handler: NextHandler, callback: CallbackQuery, data: dict[str, Any]
    ) -> Any:
        notice = (callback.message.chat.id, callback.message.message_id)
        if notice in self._busy_notices:
            await acknowledge(callback, texts.ACTION_BUSY_NOTICE)
            return None
        self._busy_notices.add(notice)
        try:
            return await handler(callback, data)
        finally:
            self._busy_notices.discard(notice)


def build_router() -> Router:
    router = Router(name=__name__)
    router.callback_query.filter(is_admin_button_in_private_chat)
    router.callback_query.middleware(stop_spinner_on_failure)
    router.callback_query.middleware(_OnePressPerNotice())
    router.callback_query.register(handle_add_unlisted, AddUnlistedButton.filter())
    router.callback_query.register(handle_kick, KickButton.filter())
    router.callback_query.register(handle_add_declined, AddDeclinedButton.filter())
    router.callback_query.register(handle_decide_request, DecideRequestButton.filter())
    router.callback_query.register(handle_ask_forget_group, AskForgetGroupButton.filter())
    router.callback_query.register(handle_cancel_forget_group, CancelForgetGroupButton.filter())
    router.callback_query.register(handle_confirm_forget_group, ConfirmForgetGroupButton.filter())
    return router


async def handle_add_unlisted(
    callback: CallbackQuery, callback_data: AddUnlistedButton, bot: Bot, services: Services
) -> None:
    chat_key, user_id = callback_data.chat_key, callback_data.user_id
    chat_member = await look_up_chat_member(bot, chat_key, user_id)
    ref = _build_ref(chat_member, user_id)
    report = await apply_member_operation(ADD_MEMBERS, chat_key, [ref], services)
    if chat_member is not None:
        await confirm_member_in_chat(chat_key, chat_member, services)
    await _close_notice(callback, report or texts.GROUP_GONE_NOTICE)


async def handle_add_declined(
    callback: CallbackQuery, callback_data: AddDeclinedButton, bot: Bot, services: Services
) -> None:
    chat_key, user_id = callback_data.chat_key, callback_data.user_id
    chat_member = await look_up_chat_member(bot, chat_key, user_id)
    ref = _build_ref(chat_member, user_id)
    report = await apply_member_operation(ADD_MEMBERS, chat_key, [ref], services)
    result = f"{report}\n{texts.APPLY_AGAIN_HINT}" if report else texts.GROUP_GONE_NOTICE
    await _close_notice(callback, result)


async def handle_kick(
    callback: CallbackQuery, callback_data: KickButton, bot: Bot, services: Services
) -> None:
    chat_key, user_id = callback_data.chat_key, callback_data.user_id
    chat_id = int(chat_key)
    group = services.whitelist_store.read().groups.get(chat_key)
    chat_member = await look_up_chat_member(bot, chat_key, user_id)
    if group is not None and group.has_member(_build_ref(chat_member, user_id)):
        await _close_notice(callback, texts.ALREADY_LISTED_RESULT)
        return
    try:
        await call_with_retry(lambda: bot.ban_chat_member(chat_id, user_id))
    except AiogramError as error:
        logger.warning("Could not remove user %s from chat %s: %s", user_id, chat_id, error)
        await acknowledge(callback, texts.KICK_FAILED_NOTICE)
        return
    project = group.project if group else chat_key
    await _close_notice(callback, await _lift_ban(bot, chat_id, user_id, project, services))


async def handle_decide_request(
    callback: CallbackQuery, callback_data: DecideRequestButton, bot: Bot, services: Services
) -> None:
    """Decide first and tell the person after: a wrong message is worse than none."""
    chat_key, user_id = callback_data.chat_key, callback_data.user_id
    chat_id = int(chat_key)
    decide = (
        bot.approve_chat_join_request if callback_data.approve else bot.decline_chat_join_request
    )
    try:
        await call_with_retry(lambda: decide(chat_id, user_id))
    except AiogramError as error:
        await _report_decision_failure(callback, error)
        return

    project = _find_project_name(chat_key, services)
    if callback_data.approve:
        # Listed, so that the person's arrival does not raise an alarm about an intruder.
        await _list_approved_person(bot, chat_key, user_id, services)
        services.audit_log.record_request_approved_manually(user_id, project)
        direct_message, result = (
            texts.format_approved_direct_message(project),
            texts.APPROVED_RESULT,
        )
    else:
        services.audit_log.record_request_declined_manually(user_id, project)
        direct_message, result = texts.DECLINED_DIRECT_MESSAGE, texts.DECLINED_RESULT
    is_told = await services.notifier.send_direct_message(user_id, direct_message)
    await _close_notice(callback, result if is_told else f"{result}\n{texts.PERSON_NOT_TOLD_HINT}")


async def handle_ask_forget_group(
    callback: CallbackQuery, callback_data: AskForgetGroupButton
) -> None:
    await acknowledge(callback, texts.FORGET_WARNING_NOTICE)
    await _swap_keyboard(callback, build_forget_confirmation_keyboard(callback_data.chat_key))


async def handle_cancel_forget_group(
    callback: CallbackQuery, callback_data: CancelForgetGroupButton
) -> None:
    await acknowledge(callback)
    await _swap_keyboard(callback, build_removed_bot_keyboard(callback_data.chat_key))


async def handle_confirm_forget_group(
    callback: CallbackQuery, callback_data: ConfirmForgetGroupButton, services: Services
) -> None:
    outcome = await forget_inactive_group(callback_data.chat_key, services)
    await _close_notice(callback, _FORGET_RESULTS[outcome])


def _build_ref(chat_member: ChatMember | None, user_id: int) -> MemberRef:
    """Name a person with their username too, which is how an entry may be listed."""
    return build_person(chat_member.user).ref if chat_member else MemberRef(user_id=user_id)


async def _lift_ban(bot: Bot, chat_id: int, user_id: int, project: str, services: Services) -> str:
    """End the ban at once, so that removal does not bar a later request. Returns the outcome."""
    try:
        await call_with_retry(lambda: bot.unban_chat_member(chat_id, user_id, only_if_banned=True))
    except AiogramError as error:
        logger.warning("Could not lift the ban of user %s in chat %s: %s", user_id, chat_id, error)
        services.audit_log.record_member_left_banned(user_id, project)
        return texts.KICKED_BUT_BANNED_RESULT
    services.audit_log.record_member_kicked(user_id, project)
    return texts.KICKED_RESULT


async def _list_approved_person(bot: Bot, chat_key: str, user_id: int, services: Services) -> None:
    chat_member = await look_up_chat_member(bot, chat_key, user_id)
    ref = _build_ref(chat_member, user_id)
    try:
        await apply_member_operation(ADD_MEMBERS, chat_key, [ref], services)
    except WhitelistCorruptedError as error:
        logger.warning("Could not list approved user %s: %s", user_id, error)


async def _report_decision_failure(callback: CallbackQuery, error: AiogramError) -> None:
    if is_request_already_resolved(error):
        await _close_notice(callback, texts.ALREADY_RESOLVED_RESULT)
    else:
        logger.warning("Manual decision on a join request failed: %s", error)
        await acknowledge(callback, texts.DECISION_FAILED_NOTICE)


def _find_project_name(chat_key: str, services: Services) -> str:
    """Name the project; deciding must work even when the access list cannot be read."""
    try:
        group = services.whitelist_store.read().groups.get(chat_key)
    except WhitelistCorruptedError:
        return texts.UNKNOWN_PROJECT
    return group.project if group else texts.UNKNOWN_PROJECT


async def _close_notice(callback: CallbackQuery, result: str) -> None:
    await acknowledge(callback)
    await edit_ignoring_no_change(
        callback.message.edit_text(f"{callback.message.html_text}\n\n{result}")
    )


async def _swap_keyboard(callback: CallbackQuery, keyboard: InlineKeyboardMarkup) -> None:
    await edit_ignoring_no_change(callback.message.edit_reply_markup(reply_markup=keyboard))
