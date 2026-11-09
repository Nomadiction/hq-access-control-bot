"""Admin commands, available only in a private chat with the bot."""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from hq_access_bot import texts
from hq_access_bot.audit_log import AuditLog
from hq_access_bot.config import Settings
from hq_access_bot.handlers.command_args import MemberCommandArgs, parse_target_and_members
from hq_access_bot.handlers.panel_screens import build_status_text
from hq_access_bot.handlers.telegram_mapping import (
    build_person,
    is_admin_in_private_chat,
    is_present_in_chat,
)
from hq_access_bot.services import Services
from hq_access_bot.whitelist.identity import MemberRef, ObservedMember
from hq_access_bot.whitelist.models import Group, Member, MemberChange, Whitelist

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _MemberOperation:
    """The steps in which adding and removing members differ."""

    usage: str
    apply: Callable[[Group, Iterable[MemberRef]], MemberChange]
    record: Callable[[AuditLog, str, list[str]], None]
    format_report: Callable[[str, MemberChange], str]


_MEMBER_OPERATIONS = {
    "add": _MemberOperation(
        texts.ADD_USAGE, Group.add_all, AuditLog.record_members_added, texts.format_add_report
    ),
    "remove": _MemberOperation(
        texts.REMOVE_USAGE,
        Group.remove_all,
        AuditLog.record_members_removed,
        texts.format_removal_report,
    ),
}


def build_router() -> Router:
    router = Router(name=__name__)
    router.message.filter(_is_admin_in_private_chat)
    router.message.register(handle_status, Command("status"))
    router.message.register(handle_member_change, Command(*_MEMBER_OPERATIONS))
    router.message.register(handle_delete_group, Command("delgroup"))
    router.message.register(handle_reload, Command("reload"))
    return router


async def handle_status(message: Message, services: Services, started_at_seconds: float) -> None:
    await message.answer(build_status_text(services.whitelist_store.read(), started_at_seconds))


async def handle_member_change(
    message: Message, command: CommandObject, services: Services
) -> None:
    operation = _MEMBER_OPERATIONS[command.command]
    snapshot = services.whitelist_store.read()
    args = parse_target_and_members(command.args, snapshot)
    if args.invalid:
        await message.answer(texts.format_invalid_usernames(args.invalid))
    elif not args.target or not args.refs:
        await message.answer(operation.usage)
    else:
        chat_key = await _resolve_chat_key(message, args.target, snapshot)
        if chat_key is not None:
            await _apply_member_operation(message, operation, chat_key, args, services)


async def handle_delete_group(message: Message, command: CommandObject, services: Services) -> None:
    target = (command.args or "").strip()
    if not target:
        await message.answer(texts.DELGROUP_USAGE)
        return

    chat_key = await _resolve_chat_key(message, target, services.whitelist_store.read())
    if chat_key is None:
        return
    async with services.whitelist_store.transaction() as whitelist:
        group = whitelist.remove_group(chat_key)

    if group is None:
        await message.answer(texts.format_group_not_found(target))
        return
    services.audit_log.record_group_deleted_by_admin(chat_key, group.project)
    await message.answer(texts.format_group_deleted_reply(group.project))


async def handle_reload(message: Message, bot: Bot, services: Services) -> None:
    """Check the list against Telegram, save the result and show it."""
    store = services.whitelist_store
    snapshot = store.read()
    if not snapshot.groups:
        await message.answer(texts.EMPTY_WHITELIST)
        return

    observed = await _observe_all_members(bot, snapshot)
    async with store.transaction() as whitelist:
        whitelist.reconcile(observed)
    for text in texts.format_access_list_messages(whitelist):
        await message.answer(text)


async def _resolve_chat_key(message: Message, target: str, whitelist: Whitelist) -> str | None:
    """Return the only group a target names, or tell the admin why there is none."""
    chat_keys = whitelist.find_group_keys(target)
    if len(chat_keys) == 1:
        return chat_keys[0]
    await message.answer(
        texts.format_group_ambiguous(target, {key: whitelist.groups[key] for key in chat_keys})
        if chat_keys
        else texts.format_group_not_found(target)
    )
    return None


async def _apply_member_operation(
    message: Message,
    operation: _MemberOperation,
    chat_key: str,
    args: MemberCommandArgs,
    services: Services,
) -> None:
    async with services.whitelist_store.transaction() as whitelist:
        group = whitelist.groups.get(chat_key)
        change = operation.apply(group, args.refs) if group else None

    if change is None:
        await message.answer(texts.format_group_not_found(args.target))
        return
    if change.applied:
        operation.record(services.audit_log, group.project, change.applied)
    await message.answer(operation.format_report(group.project, change))


async def _is_admin_in_private_chat(message: Message, settings: Settings) -> bool:
    return is_admin_in_private_chat(message.chat, message.from_user, settings.admin_ids)


async def _observe_all_members(
    bot: Bot, whitelist: Whitelist
) -> dict[str, dict[int, ObservedMember]]:
    """Poll Telegram. A member that could not be checked is left out of the result."""
    observed: dict[str, dict[int, ObservedMember]] = {}
    for chat_key, group in whitelist.groups.items():
        if group.is_active:
            observed[chat_key] = await _observe_group(bot, int(chat_key), group)
    return observed


async def _observe_group(bot: Bot, chat_id: int, group: Group) -> dict[int, ObservedMember]:
    known_members = [m for m in group.members if m.user_id is not None]
    results = {m.user_id: await _observe_member(bot, chat_id, m) for m in known_members}
    return {user_id: seen for user_id, seen in results.items() if seen is not None}


async def _observe_member(bot: Bot, chat_id: int, member: Member) -> ObservedMember | None:
    try:
        chat_member = await bot.get_chat_member(chat_id, member.user_id)
    except TelegramAPIError as error:
        logger.warning("Could not check member %s of chat %s: %s", member.user_id, chat_id, error)
        return None
    return ObservedMember(
        person=build_person(chat_member.user),
        is_in_group=is_present_in_chat(chat_member),
        was_joined=member.has_joined,
    )
