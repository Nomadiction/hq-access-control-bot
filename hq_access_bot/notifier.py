"""Delivery of direct messages; an unreachable recipient is not an error."""

import logging
import time

from aiogram import Bot
from aiogram.exceptions import AiogramError

logger = logging.getLogger(__name__)

_ALERT_INTERVAL_SECONDS = 600


class Notifier:
    def __init__(self, bot: Bot, admin_ids: frozenset[int]) -> None:
        self._bot = bot
        self._admin_ids = admin_ids
        self._last_alert_seconds: dict[str, float] = {}

    async def send_direct_message(self, chat_id: int, text: str) -> bool:
        """Return whether the message was delivered. A failure never reaches the caller."""
        try:
            await self._bot.send_message(chat_id, text)
        except AiogramError as error:
            logger.warning("DM to chat %s not delivered: %s", chat_id, error)
            return False
        return True

    async def notify_admins(self, text: str) -> bool:
        """Return whether at least one admin received the message."""
        delivered = [await self.send_direct_message(admin_id, text) for admin_id in self._admin_ids]
        return any(delivered)

    async def alert_admins(self, alert_key: str, text: str) -> None:
        """Tell admins about a failure, at most once per interval for the same key."""
        now = time.monotonic()
        last_alert = self._last_alert_seconds.get(alert_key)
        if last_alert is not None and now - last_alert < _ALERT_INTERVAL_SECONDS:
            return
        if await self.notify_admins(text):
            self._last_alert_seconds[alert_key] = now
