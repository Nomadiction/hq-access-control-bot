"""Reaction to changes in the bot's own status in chats."""

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import ChatMemberAdministrator, ChatMemberUpdated, Message

from hq_access_bot import texts
from hq_access_bot.handlers.telegram_mapping import (
    DEPARTED_STATUSES,
    PRESENT_STATUSES,
    build_chat_key,
    build_project_name,
)
from hq_access_bot.services import Services
from hq_access_bot.whitelist.models import GroupRegistration

_GROUP_CHAT_TYPES = frozenset({ChatType.GROUP, ChatType.SUPERGROUP})
_PROMOTABLE_STATUSES = frozenset({ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED})
_ADMIN_STATUSES = frozenset({ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR})


def build_router() -> Router:
    router = Router(name=__name__)
    router.my_chat_member.register(handle_bot_status_change)
    router.message.register(handle_group_renamed, F.new_chat_title)
    return router


async def handle_bot_status_change(event: ChatMemberUpdated, services: Services) -> None:
    # A user blocking or unblocking the bot arrives here too, as a private chat.
    if event.chat.type not in _GROUP_CHAT_TYPES:
        return
    new_status = event.new_chat_member.status
    if new_status in DEPARTED_STATUSES:
        await _deactivate_group(event, services)
    elif new_status in PRESENT_STATUSES:
        if event.chat.type == ChatType.SUPERGROUP:
            await _track_supergroup(event, services)
        elif event.old_chat_member.status in DEPARTED_STATUSES:
            await services.notifier.notify_admins(
                texts.format_basic_group_notice(build_project_name(event.chat.title, event.chat))
            )


async def handle_group_renamed(message: Message, services: Services) -> None:
    chat_key = build_chat_key(message.chat)
    title = build_project_name(message.new_chat_title, message.chat)
    async with services.whitelist_store.transaction() as whitelist:
        was_renamed = whitelist.rename_group(chat_key, title)
    if was_renamed:
        services.audit_log.record_group_renamed(chat_key, title)
        await services.notifier.notify_admins(texts.format_group_renamed_notice(title))


async def _deactivate_group(event: ChatMemberUpdated, services: Services) -> None:
    chat_key = build_chat_key(event.chat)
    async with services.whitelist_store.transaction() as whitelist:
        was_active = whitelist.deactivate_group(chat_key)
    if was_active:
        title = build_project_name(event.chat.title, event.chat)
        services.audit_log.record_group_deactivated(chat_key, title)
        await services.notifier.notify_admins(texts.format_bot_removed_notice(title, chat_key))


async def _track_supergroup(event: ChatMemberUpdated, services: Services) -> None:
    chat_key = build_chat_key(event.chat)
    title = build_project_name(event.chat.title, event.chat)
    async with services.whitelist_store.transaction() as whitelist:
        registration = whitelist.register_group(chat_key, title)
    if registration is GroupRegistration.NEW:
        services.audit_log.record_group_registered(chat_key, title)
        await services.notifier.notify_admins(texts.format_group_registered_notice(title))
    elif registration is GroupRegistration.RESTORED:
        services.audit_log.record_group_restored(chat_key, title)
        await services.notifier.notify_admins(texts.format_group_restored_notice(title))
    elif _is_promotion(event):
        await services.notifier.notify_admins(texts.format_bot_promoted_notice(title))
    elif _is_demotion(event):
        await services.notifier.notify_admins(texts.format_bot_demoted_notice(title))
    if not _can_process_join_requests(event) and not _is_demotion(event):
        await services.notifier.notify_admins(texts.format_missing_rights_notice(title))


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


def _can_process_join_requests(event: ChatMemberUpdated) -> bool:
    bot_member = event.new_chat_member
    return isinstance(bot_member, ChatMemberAdministrator) and bot_member.can_invite_users
