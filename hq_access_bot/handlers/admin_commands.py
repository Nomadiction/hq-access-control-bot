"""Admin commands, available only in a private chat with the bot."""

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from hq_access_bot import texts
from hq_access_bot.handlers.access_list_changes import (
    ADD_MEMBERS,
    REMOVE_MEMBERS,
    apply_member_operation,
    delete_group,
    sync_with_telegram,
)
from hq_access_bot.handlers.command_args import parse_target_and_members
from hq_access_bot.handlers.panel_screens import build_status_text
from hq_access_bot.handlers.telegram_mapping import is_admin_message_in_private_chat
from hq_access_bot.services import Services
from hq_access_bot.whitelist.models import Whitelist

_MEMBER_COMMANDS = {
    "add": (ADD_MEMBERS, texts.ADD_USAGE),
    "remove": (REMOVE_MEMBERS, texts.REMOVE_USAGE),
}


def build_router() -> Router:
    router = Router(name=__name__)
    router.message.filter(is_admin_message_in_private_chat)
    router.message.register(handle_status, Command("status"))
    router.message.register(handle_member_change, Command(*_MEMBER_COMMANDS))
    router.message.register(handle_delete_group, Command("delgroup"))
    router.message.register(handle_reload, Command("reload"))
    return router


async def handle_status(message: Message, services: Services, started_at_seconds: float) -> None:
    await message.answer(build_status_text(services.whitelist_store.read(), started_at_seconds))


async def handle_member_change(
    message: Message, command: CommandObject, services: Services
) -> None:
    operation, usage = _MEMBER_COMMANDS[command.command]
    snapshot = services.whitelist_store.read()
    args = parse_target_and_members(command.args, snapshot)
    if args.invalid:
        await message.answer(texts.format_invalid_usernames(args.invalid))
    elif not args.target or not args.refs:
        await message.answer(usage)
    else:
        chat_key = await _resolve_chat_key(message, args.target, snapshot)
        if chat_key is not None:
            report = await apply_member_operation(operation, chat_key, args.refs, services)
            await message.answer(report or texts.format_group_not_found(args.target))


async def handle_delete_group(message: Message, command: CommandObject, services: Services) -> None:
    target = (command.args or "").strip()
    if not target:
        await message.answer(texts.DELGROUP_USAGE)
        return

    chat_key = await _resolve_chat_key(message, target, services.whitelist_store.read())
    if chat_key is None:
        return
    group = await delete_group(chat_key, services)
    if group is None:
        await message.answer(texts.format_group_not_found(target))
        return
    await message.answer(texts.format_group_deleted_reply(group.project))


async def handle_reload(message: Message, bot: Bot, services: Services) -> None:
    """Check the list against Telegram, save the result and show it."""
    if not services.whitelist_store.read().groups:
        await message.answer(texts.EMPTY_WHITELIST)
        return

    whitelist = await sync_with_telegram(bot, services)
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
