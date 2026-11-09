"""Admin commands, available only in a private chat with the bot."""

import time

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from hq_access_bot import texts
from hq_access_bot.config import Settings
from hq_access_bot.handlers.command_args import parse_target_and_members
from hq_access_bot.handlers.telegram_mapping import DEPARTED_STATUSES, build_person
from hq_access_bot.services import Services
from hq_access_bot.whitelist.models import AddOutcome, ObservedMember, Whitelist


def build_router() -> Router:
    router = Router(name=__name__)
    router.message.filter(_is_admin_in_private_chat)
    router.message.register(handle_status, Command("status"))
    router.message.register(handle_add, Command("add"))
    router.message.register(handle_remove, Command("remove"))
    router.message.register(handle_delete_group, Command("delgroup"))
    router.message.register(handle_reload, Command("reload"))
    return router


async def handle_status(message: Message, services: Services, started_at_seconds: float) -> None:
    whitelist = services.whitelist_store.read()
    await message.answer(
        texts.format_status_report(
            uptime_seconds=int(time.time() - started_at_seconds),
            group_count=len(whitelist.groups),
            member_count=whitelist.count_unique_members(),
        )
    )


async def handle_add(message: Message, command: CommandObject, services: Services) -> None:
    target, refs = parse_target_and_members(command.args)
    if not target or not refs:
        await message.answer(texts.ADD_USAGE)
        return

    async with services.whitelist_store.transaction() as whitelist:
        group = whitelist.find_group(target)
        outcome = group.add_all(refs) if group else AddOutcome([], [])

    if group is None:
        await message.answer(texts.format_group_not_found(target))
        return
    if outcome.added:
        services.audit_log.record_members_added(group.project, outcome.added)
    await message.answer(texts.format_add_report(group.project, outcome))


async def handle_remove(message: Message, command: CommandObject, services: Services) -> None:
    target, refs = parse_target_and_members(command.args)
    if not target or not refs:
        await message.answer(texts.REMOVE_USAGE)
        return

    async with services.whitelist_store.transaction() as whitelist:
        group = whitelist.find_group(target)
        removed = group.remove_all(refs) if group else []

    if group is None:
        await message.answer(texts.format_group_not_found(target))
        return
    if removed:
        services.audit_log.record_members_removed(group.project, removed)
    await message.answer(texts.format_removal_report(group.project, removed))


async def handle_delete_group(message: Message, command: CommandObject, services: Services) -> None:
    target = (command.args or "").strip()
    if not target:
        await message.answer(texts.DELGROUP_USAGE)
        return

    async with services.whitelist_store.transaction() as whitelist:
        chat_key = whitelist.find_group_key(target)
        group = whitelist.remove_group(chat_key) if chat_key is not None else None

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
    await message.answer(texts.format_access_lists(whitelist))


async def _is_admin_in_private_chat(message: Message, settings: Settings) -> bool:
    return message.chat.type == ChatType.PRIVATE and message.from_user.id in settings.admin_ids


async def _observe_all_members(
    bot: Bot, whitelist: Whitelist
) -> dict[str, dict[int, ObservedMember]]:
    """Poll Telegram. A member that could not be checked is left out of the result."""
    observed: dict[str, dict[int, ObservedMember]] = {}
    for chat_key, group in whitelist.groups.items():
        known_ids = [m.user_id for m in group.members if m.user_id is not None]
        results = {uid: await _observe_member(bot, int(chat_key), uid) for uid in known_ids}
        observed[chat_key] = {uid: seen for uid, seen in results.items() if seen is not None}
    return observed


async def _observe_member(bot: Bot, chat_id: int, user_id: int) -> ObservedMember | None:
    try:
        chat_member = await bot.get_chat_member(chat_id, user_id)
    except TelegramAPIError:
        return None
    return ObservedMember(
        person=build_person(chat_member.user),
        is_in_group=chat_member.status not in DEPARTED_STATUSES,
    )
