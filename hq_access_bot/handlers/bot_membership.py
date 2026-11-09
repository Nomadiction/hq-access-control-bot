"""Reaction to changes in the bot's own status in chats."""

from aiogram import Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import ChatMemberUpdated

from hq_access_bot import texts
from hq_access_bot.handlers.telegram_mapping import (
    DEPARTED_STATUSES,
    PRESENT_STATUSES,
    build_chat_key,
)
from hq_access_bot.services import Services

_GROUP_CHAT_TYPES = frozenset({ChatType.GROUP, ChatType.SUPERGROUP})
_PROMOTABLE_STATUSES = frozenset({ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED})
_ADMIN_STATUSES = frozenset({ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR})


def build_router() -> Router:
    router = Router(name=__name__)
    router.my_chat_member.register(handle_bot_status_change)
    return router


async def handle_bot_status_change(event: ChatMemberUpdated, services: Services) -> None:
    # A user blocking or unblocking the bot arrives here too, as a private chat.
    if event.chat.type not in _GROUP_CHAT_TYPES:
        return
    new_status = event.new_chat_member.status
    if new_status in DEPARTED_STATUSES:
        await _forget_group(event, services)
    elif new_status in PRESENT_STATUSES:
        if event.chat.type == ChatType.SUPERGROUP:
            await _track_supergroup(event, services)
        elif event.old_chat_member.status in DEPARTED_STATUSES:
            await services.notifier.notify_admins(
                texts.format_basic_group_notice(_get_chat_title(event))
            )


async def _forget_group(event: ChatMemberUpdated, services: Services) -> None:
    chat_key = build_chat_key(event.chat)
    async with services.whitelist_store.transaction() as whitelist:
        removed_group = whitelist.remove_group(chat_key)
    if removed_group is not None:
        title = _get_chat_title(event)
        services.audit_log.record_group_lost(chat_key, title)
        await services.notifier.notify_admins(texts.format_bot_removed_notice(title))


async def _track_supergroup(event: ChatMemberUpdated, services: Services) -> None:
    chat_key = build_chat_key(event.chat)
    title = _get_chat_title(event)
    async with services.whitelist_store.transaction() as whitelist:
        is_new_group = whitelist.register_group(chat_key, title)
    if is_new_group:
        services.audit_log.record_group_registered(chat_key, title)
        await services.notifier.notify_admins(texts.format_group_registered_notice(title))
    elif _is_promotion(event):
        await services.notifier.notify_admins(texts.format_bot_promoted_notice(title))
    elif _is_demotion(event):
        await services.notifier.notify_admins(texts.format_bot_demoted_notice(title))


def _is_promotion(event: ChatMemberUpdated) -> bool:
    return (
        event.new_chat_member.status == ChatMemberStatus.ADMINISTRATOR
        and event.old_chat_member.status in _PROMOTABLE_STATUSES
    )


def _is_demotion(event: ChatMemberUpdated) -> bool:
    return (
        event.new_chat_member.status == ChatMemberStatus.MEMBER
        and event.old_chat_member.status in _ADMIN_STATUSES
    )


def _get_chat_title(event: ChatMemberUpdated) -> str:
    return event.chat.title or str(event.chat.id)
