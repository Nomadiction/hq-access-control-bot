from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import DeleteWebhook, SetMyCommands, SetMyDescription

from hq_access_bot import app, instance_lock
from hq_access_bot.whitelist.store import WhitelistCorruptedError
from tests.support import ADMIN_ID


async def test_startup_keeps_updates_received_while_the_bot_was_off(
    harness, settings, offline_serve
):
    await app.serve(settings, harness.paths)

    assert harness.calls_of(DeleteWebhook)[0].drop_pending_updates is False


async def test_startup_gives_admins_their_own_command_menu(harness, settings, offline_serve):
    await app.serve(settings, harness.paths)

    default_menu, admin_menu = harness.calls_of(SetMyCommands)
    assert "status" not in {c.command for c in default_menu.commands}
    assert "status" in {c.command for c in admin_menu.commands}
    assert admin_menu.scope.chat_id == ADMIN_ID


async def test_profile_failure_does_not_stop_startup(harness, settings, offline_serve):
    harness.session.failing_methods.add(SetMyDescription)

    await app.serve(settings, harness.paths)

    assert len(harness.calls_of(SetMyCommands)) == 2
    offline_serve.assert_awaited_once()


def test_handlers_subscribe_to_chat_member_updates(harness):
    # Telegram sends chat_member only to bots that explicitly request it.
    used_updates = harness.dispatcher.resolve_used_update_types()

    assert {"chat_join_request", "chat_member", "my_chat_member", "message"} <= set(used_updates)


class HeldLockFcntl:
    """Stands in for fcntl: the first lock succeeds, the next acts like a held file."""

    LOCK_EX = 2
    LOCK_NB = 4

    def __init__(self):
        self.is_held = False

    def flock(self, lock_file, operation):
        if self.is_held:
            raise OSError
        self.is_held = True


def test_second_instance_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(instance_lock, "fcntl", HeldLockFcntl())
    lock_path = tmp_path / "bot.lock"

    with (
        instance_lock.hold_instance_lock(lock_path),
        pytest.raises(instance_lock.InstanceAlreadyRunningError),
        instance_lock.hold_instance_lock(lock_path),
    ):
        pass


def test_platform_without_flock_runs_unguarded(tmp_path, monkeypatch):
    monkeypatch.setattr(instance_lock, "fcntl", None)
    entered = False

    with instance_lock.hold_instance_lock(tmp_path / "bot.lock"):
        entered = True

    assert entered


@pytest.fixture
def offline_serve(harness, monkeypatch):
    """Give serve its real dependencies but replace the network and endless polling."""

    def build_offline_bot(token, default):
        return Bot(token=token, session=harness.session, default=default)

    polling = AsyncMock()
    monkeypatch.setattr(app, "Bot", build_offline_bot)
    monkeypatch.setattr(Dispatcher, "start_polling", polling)
    return polling


async def test_serve_prepares_the_bot_and_starts_polling(harness, settings, offline_serve):
    await app.serve(settings, harness.paths)

    assert harness.calls_of(DeleteWebhook)
    offline_serve.assert_awaited_once()


async def test_serve_refuses_corrupted_whitelist_before_touching_telegram(
    harness, settings, offline_serve
):
    harness.paths.whitelist.write_text("{ broken", encoding="utf-8")

    with pytest.raises(WhitelistCorruptedError):
        await app.serve(settings, harness.paths)

    assert harness.session.calls == []
    offline_serve.assert_not_awaited()
