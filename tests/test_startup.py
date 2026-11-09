import runpy
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import DeleteWebhook, GetMe, SendMessage, SetMyCommands, SetMyDescription

from hq_access_bot import app, instance_lock
from hq_access_bot.config import ConfigurationError, DataPaths
from hq_access_bot.errors import FatalBotError
from hq_access_bot.whitelist.store import WhitelistCorruptedError
from tests.support import (
    ADMIN_ID,
    command,
    decode_error,
    network_failure,
    retry_after,
    server_error,
    unauthorized,
)


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


async def test_every_command_in_the_menus_is_answered(harness, settings, offline_serve):
    await app.serve(settings, harness.paths)
    menu_names = {c.command for menu in harness.calls_of(SetMyCommands) for c in menu.commands}

    for name in sorted(menu_names):
        harness.session.calls.clear()
        await harness.feed(command(f"/{name}"))
        assert harness.calls_of(SendMessage), name


async def test_profile_failure_does_not_stop_startup(harness, settings, offline_serve):
    harness.session.failing_methods.add(SetMyDescription)

    await app.serve(settings, harness.paths)

    assert len(harness.calls_of(SetMyCommands)) == 2
    offline_serve.assert_awaited_once()


def test_handlers_subscribe_to_chat_member_updates(harness):
    # Telegram sends chat_member only to bots that explicitly request it.
    used_updates = harness.dispatcher.resolve_used_update_types()

    assert {"chat_join_request", "chat_member", "my_chat_member", "message"} <= set(used_updates)


def test_second_instance_is_refused(tmp_path):
    lock_path = tmp_path / "bot.lock"

    with (
        instance_lock.hold_instance_lock(lock_path),
        pytest.raises(instance_lock.InstanceAlreadyRunningError),
        instance_lock.hold_instance_lock(lock_path),
    ):
        pass


def test_lock_is_released_when_the_instance_stops(tmp_path):
    lock_path = tmp_path / "bot.lock"

    with instance_lock.hold_instance_lock(lock_path):
        pass

    with instance_lock.hold_instance_lock(lock_path):
        pass


@pytest.mark.parametrize(
    "failure", [network_failure(), server_error(), decode_error(), retry_after(0)]
)
async def test_startup_waits_for_telegram(harness, settings, offline_serve, monkeypatch, failure):
    monkeypatch.setattr(app, "_STARTUP_RETRY_PAUSE_SECONDS", 0)
    harness.session.script_errors(DeleteWebhook, failure, failure)

    await app.serve(settings, harness.paths)

    assert len(harness.calls_of(DeleteWebhook)) == 3
    offline_serve.assert_awaited_once()


async def test_startup_also_waits_for_the_bot_identity(
    harness, settings, offline_serve, monkeypatch
):
    monkeypatch.setattr(app, "_STARTUP_RETRY_PAUSE_SECONDS", 0)
    harness.session.script_errors(GetMe, network_failure())

    await app.serve(settings, harness.paths)

    assert len(harness.calls_of(DeleteWebhook)) == 2
    offline_serve.assert_awaited_once()


async def test_rejected_token_stops_startup_with_a_clear_error(harness, settings, offline_serve):
    harness.session.script_errors(DeleteWebhook, unauthorized())

    with pytest.raises(ConfigurationError, match="BOT_TOKEN"):
        await app.serve(settings, harness.paths)

    offline_serve.assert_not_awaited()


async def test_first_start_creates_the_list_file(tmp_path, settings, offline_serve):
    data_dir = tmp_path / "fresh"
    data_dir.mkdir()
    paths = DataPaths.inside(data_dir)

    await app.serve(settings, paths)

    assert paths.whitelist.read_text(encoding="utf-8").strip() == "{}"


async def test_list_lost_after_the_first_start_is_refused(harness, settings, offline_serve):
    harness.paths.whitelist.unlink()

    with pytest.raises(WhitelistCorruptedError):
        await app.serve(settings, harness.paths)

    assert harness.session.calls == []
    assert not harness.paths.whitelist.exists()


def run_entry_point(monkeypatch, error):
    monkeypatch.setattr(app, "run", Mock(side_effect=error))
    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("hq_access_bot", run_name="__main__")
    return stopped.value.code


def test_ctrl_c_exits_without_a_traceback(monkeypatch):
    assert run_entry_point(monkeypatch, KeyboardInterrupt()) == 0


def test_fatal_error_exits_with_its_message(monkeypatch):
    assert run_entry_point(monkeypatch, FatalBotError("broken setup")) == "broken setup"
