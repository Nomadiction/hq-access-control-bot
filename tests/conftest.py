import json
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import count
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import InlineKeyboardButton

from hq_access_bot import history_cleaner, telegram_retry
from hq_access_bot.app import build_dispatcher
from hq_access_bot.audit_log import AuditLog
from hq_access_bot.config import DataPaths, Settings
from hq_access_bot.history_cleaner import HistoryCleaner
from hq_access_bot.notifier import Notifier
from hq_access_bot.services import Services
from hq_access_bot.whitelist.store import WhitelistStore
from tests.support import (
    ADMIN_ID,
    FAKE_TOKEN,
    HeldCleanup,
    RecordingSession,
    button_press,
    command,
)


@dataclass
class BotHarness:
    """The real dispatcher with all its dependencies, cut off from the network."""

    session: RecordingSession
    bot: Bot
    dispatcher: Dispatcher
    paths: DataPaths
    update_ids: Iterator[int]

    async def feed(self, update: dict[str, Any]) -> None:
        await self.dispatcher.feed_raw_update(
            self.bot, {"update_id": next(self.update_ids), **update}
        )

    def given_whitelist(self, content: dict[str, Any]) -> None:
        self.paths.whitelist.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")

    def whitelist_on_disk(self) -> dict[str, Any]:
        return json.loads(self.paths.whitelist.read_text(encoding="utf-8"))

    def members_on_disk(self, chat_key: str) -> list[dict[str, Any]]:
        return self.whitelist_on_disk()[chat_key]["members"]

    def calls_of(self, method_type: type) -> list[Any]:
        return [call for call in self.session.calls if isinstance(call, method_type)]

    def texts_sent_to(self, chat_id: int) -> list[str]:
        return [call.text for call in self.calls_of(SendMessage) if call.chat_id == chat_id]

    def admin_notices(self) -> list[str]:
        return self.texts_sent_to(ADMIN_ID)

    def current_screen(self) -> SendMessage | EditMessageText:
        """The latest text the bot showed, sent as a new message or by editing one."""
        return next(
            call
            for call in reversed(self.session.calls)
            if isinstance(call, SendMessage | EditMessageText)
        )

    def screen_buttons(self) -> list[InlineKeyboardButton]:
        keyboard = self.current_screen().reply_markup
        return [button for row in keyboard.inline_keyboard for button in row] if keyboard else []

    def screen_labels(self) -> list[str]:
        return [button.text for button in self.screen_buttons()]

    def screen_button(self, label: str) -> InlineKeyboardButton:
        return next(button for button in self.screen_buttons() if label in button.text)

    async def press(self, label: str) -> None:
        await self.feed(button_press(self.screen_button(label).callback_data))

    async def open_groups(self) -> None:
        await self.feed(command("/start"))
        await self.press("Группы")

    def last_toast(self) -> str | None:
        return self.calls_of(AnswerCallbackQuery)[-1].text

    def audit_events(self) -> list[str]:
        if not self.paths.audit_log.exists():
            return []
        lines = self.paths.audit_log.read_text(encoding="utf-8").splitlines()
        return [line.split(" ", 2)[2] for line in lines]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        bot_token=FAKE_TOKEN, admin_ids=frozenset({ADMIN_ID}), support_username="helpdesk"
    )


@pytest.fixture
def harness(tmp_path, settings, monkeypatch) -> Iterator[BotHarness]:
    monkeypatch.setattr(history_cleaner, "_PAUSE_BETWEEN_BATCHES_SECONDS", 0)
    monkeypatch.setattr(telegram_retry, "_NETWORK_RETRY_PAUSE_SECONDS", 0)
    paths = DataPaths.inside(tmp_path)
    session = RecordingSession()
    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    store = WhitelistStore(paths.whitelist)
    store.create_if_missing()
    audit_log = AuditLog(paths.audit_log)
    notifier = Notifier(bot, settings.admin_ids)
    services = Services(store, audit_log, notifier, HistoryCleaner(bot))
    dispatcher = build_dispatcher(settings, services)
    yield BotHarness(session, bot, dispatcher, paths, count(1))
    audit_log.close()


@pytest.fixture
def held_cleanup(monkeypatch) -> HeldCleanup:
    cleanup = HeldCleanup()
    monkeypatch.setattr(history_cleaner, "_delete_history", cleanup)
    return cleanup


@pytest.fixture
def many_groups(harness) -> BotHarness:
    harness.given_whitelist(
        {str(-1000 - i): {"project": f"Group {i:02}", "members": []} for i in reversed(range(12))}
    )
    return harness
