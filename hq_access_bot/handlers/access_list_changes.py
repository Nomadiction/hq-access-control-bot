"""Changes to the access list, shared by text commands and panel buttons."""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

from hq_access_bot import texts
from hq_access_bot.audit_log import AuditLog
from hq_access_bot.handlers.telegram_mapping import build_person, is_present_in_chat
from hq_access_bot.services import Services
from hq_access_bot.whitelist.identity import MemberRef, ObservedMember
from hq_access_bot.whitelist.models import Group, Member, MemberChange, Whitelist

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MemberOperation:
    """The steps in which adding and removing members differ."""

    apply: Callable[[Group, Iterable[MemberRef]], MemberChange]
    record: Callable[[AuditLog, str, list[str]], None]
    format_report: Callable[[str, MemberChange], str]


ADD_MEMBERS = MemberOperation(Group.add_all, AuditLog.record_members_added, texts.format_add_report)
REMOVE_MEMBERS = MemberOperation(
    Group.remove_all, AuditLog.record_members_removed, texts.format_removal_report
)


async def apply_member_operation(
    operation: MemberOperation, chat_key: str, refs: list[MemberRef], services: Services
) -> str | None:
    """Change a group's members, record it and return the report. None if it is not listed."""
    async with services.whitelist_store.transaction() as whitelist:
        group = whitelist.groups.get(chat_key)
        change = operation.apply(group, refs) if group else None

    if change is None:
        return None
    if change.applied:
        operation.record(services.audit_log, group.project, change.applied)
    return operation.format_report(group.project, change)


async def delete_group(chat_key: str, services: Services) -> Group | None:
    """Remove a group from the list and record it. None means it was already gone."""
    async with services.whitelist_store.transaction() as whitelist:
        group = whitelist.remove_group(chat_key)
    if group is not None:
        services.audit_log.record_group_deleted_by_admin(chat_key, group.project)
    return group


async def sync_with_telegram(bot: Bot, services: Services) -> Whitelist:
    """Check the list against Telegram, save the result and return it."""
    store = services.whitelist_store
    observed = await _observe_all_members(bot, store.read())
    async with store.transaction() as whitelist:
        whitelist.reconcile(observed)
    return whitelist


async def _observe_all_members(
    bot: Bot, whitelist: Whitelist
) -> dict[str, dict[int, ObservedMember]]:
    """Poll Telegram. A member that could not be checked is left out of the result."""
    observed: dict[str, dict[int, ObservedMember]] = {}
    try:
        for chat_key, group in whitelist.groups.items():
            if group.is_active:
                observed[chat_key] = await _observe_group(bot, int(chat_key), group)
    except TelegramRetryAfter as error:
        # The limit is shared with join requests, which matter more than this check.
        logger.warning("Sync with Telegram stopped by the rate limit: %s", error)
    return observed


async def _observe_group(bot: Bot, chat_id: int, group: Group) -> dict[int, ObservedMember]:
    known_members = [m for m in group.members if m.user_id is not None]
    results = {m.user_id: await _observe_member(bot, chat_id, m) for m in known_members}
    return {user_id: seen for user_id, seen in results.items() if seen is not None}


async def _observe_member(bot: Bot, chat_id: int, member: Member) -> ObservedMember | None:
    try:
        chat_member = await bot.get_chat_member(chat_id, member.user_id)
    except TelegramRetryAfter:
        raise
    except TelegramAPIError as error:
        logger.warning("Could not check member %s of chat %s: %s", member.user_id, chat_id, error)
        return None
    return ObservedMember(
        person=build_person(chat_member.user),
        is_in_group=is_present_in_chat(chat_member),
        was_joined=member.has_joined,
    )
