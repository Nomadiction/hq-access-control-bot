"""Keeps access list entries in sync with the actual group membership.

Telegram sends these events only if the bot is an administrator of the group.
"""

from aiogram import Router
from aiogram.types import ChatMemberUpdated

from hq_access_bot import texts
from hq_access_bot.handlers.telegram_mapping import (
    DEPARTED_STATUSES,
    PRESENT_STATUSES,
    build_chat_key,
    build_person,
)
from hq_access_bot.services import Services
from hq_access_bot.whitelist.identity import Person


def build_router() -> Router:
    router = Router(name=__name__)
    router.chat_member.register(handle_member_status_change)
    return router


async def handle_member_status_change(event: ChatMemberUpdated, services: Services) -> None:
    chat_key = build_chat_key(event.chat)
    group = services.whitelist_store.read().groups.get(chat_key)
    if group is None:
        return
    person = build_person(event.new_chat_member.user)
    status = event.new_chat_member.status
    if status in DEPARTED_STATUSES:
        await _remove_departed_member(chat_key, person, services)
    elif status in PRESENT_STATUSES and group.has_member(person):
        async with services.whitelist_store.transaction() as whitelist:
            whitelist.confirm_member(chat_key, person)


async def _remove_departed_member(chat_key: str, person: Person, services: Services) -> None:
    async with services.whitelist_store.transaction() as whitelist:
        group = whitelist.groups.get(chat_key)
        if group is None:
            return
        removed = group.remove_all([person.ref]).applied
    if removed:
        services.audit_log.record_member_left(person, group.project, removed)
        await services.notifier.notify_admins(
            texts.format_member_left_notice(group.project, person)
        )
