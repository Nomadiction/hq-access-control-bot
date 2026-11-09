"""Delivery of direct messages; an unreachable recipient is not an error."""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, bot: Bot, admin_ids: frozenset[int]) -> None:
        self._bot = bot
        self._admin_ids = admin_ids

    async def send_direct_message(self, user_id: int, text: str) -> None:
        """Send a direct message. Telegram blocks it unless the user has pressed Start."""
        try:
            await self._bot.send_message(user_id, text)
        except TelegramAPIError as error:
            logger.warning("DM to user %s not delivered: %s", user_id, error)

    async def notify_admins(self, text: str) -> None:
        for admin_id in self._admin_ids:
            await self.send_direct_message(admin_id, text)
