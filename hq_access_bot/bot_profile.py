"""The bot's Telegram profile: description, menu button and command lists."""

import logging
from collections.abc import Awaitable

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    MenuButtonCommands,
)

logger = logging.getLogger(__name__)

_DESCRIPTION = (
    "HQ Access Bot - пропускной контроль приватных рабочих групп. "
    "Подайте заявку по пригласительной ссылке нужного проекта: если вы в "
    "списке доступа, бот одобрит её автоматически за пару секунд. "
    "Нажмите «Start», чтобы начать."
)

_SHORT_DESCRIPTION = (
    "Контроль доступа к приватным рабочим группам. "
    "Заявки одобряются автоматически по белому списку."
)

_USER_COMMANDS = [
    BotCommand(command="start", description="Начать и показать справку"),
    BotCommand(command="help", description="Справка и возможности"),
    BotCommand(command="me", description="Показать мой ID"),
]

_ADMIN_COMMANDS = [
    BotCommand(command="start", description="Справка администратора"),
    BotCommand(command="status", description="Статус и счётчики"),
    BotCommand(command="reload", description="Показать списки доступа"),
    BotCommand(command="add", description="Добавить участников в проект"),
    BotCommand(command="remove", description="Убрать участников"),
    BotCommand(command="delgroup", description="Убрать группу из списка"),
    BotCommand(command="clear", description="Очистить переписку с ботом"),
    BotCommand(command="id", description="Узнать chat_id (в группе)"),
    BotCommand(command="me", description="Показать мой ID"),
    BotCommand(command="help", description="Справка"),
]


async def setup_bot_profile(bot: Bot, admin_ids: frozenset[int]) -> None:
    """Update the profile. The bot works without it, so failures are only logged."""
    await _apply_setting("description", bot.set_my_description(_DESCRIPTION))
    await _apply_setting("short description", bot.set_my_short_description(_SHORT_DESCRIPTION))
    await _apply_setting("menu button", bot.set_chat_menu_button(menu_button=MenuButtonCommands()))
    await _apply_setting(
        "command menu", bot.set_my_commands(_USER_COMMANDS, BotCommandScopeDefault())
    )
    for admin_id in admin_ids:
        admin_scope = BotCommandScopeChat(chat_id=admin_id)
        await _apply_setting("admin menu", bot.set_my_commands(_ADMIN_COMMANDS, admin_scope))


async def _apply_setting(setting_name: str, request: Awaitable[object]) -> None:
    try:
        await request
    except TelegramAPIError as error:
        logger.warning("Failed to set %s: %s", setting_name, error)
