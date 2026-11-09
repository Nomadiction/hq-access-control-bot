import json
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import count
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.methods import SendMessage

from hq_access_bot.app import build_dispatcher
from hq_access_bot.audit_log import AuditLog
from hq_access_bot.config import DataPaths, Settings
from hq_access_bot.handlers import public_commands
from hq_access_bot.notifier import Notifier
from hq_access_bot.services import Services
from hq_access_bot.whitelist.store import WhitelistStore
from tests.support import ADMIN_ID, FAKE_TOKEN, RecordingSession


@dataclass
class BotHarness:
    """The real dispatcher with all its dependencies, cut off from the network."""

    session: RecordingSession
    bot: Bot
    dispatcher: Dispatcher
    paths: DataPaths
    store: WhitelistStore
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
    monkeypatch.setattr(public_commands, "_PAUSE_BETWEEN_BATCHES_SECONDS", 0)
    paths = DataPaths.inside(tmp_path)
    session = RecordingSession()
    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    store = WhitelistStore(paths.whitelist)
    audit_log = AuditLog(paths.audit_log)
    notifier = Notifier(bot, settings.admin_ids)
    dispatcher = build_dispatcher(settings, Services(store, audit_log, notifier))
    yield BotHarness(session, bot, dispatcher, paths, store, count(1))
    audit_log.close()
