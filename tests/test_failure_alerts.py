import pytest
from aiogram.methods import SendMessage

from hq_access_bot import notifier as notifier_module
from hq_access_bot.notifier import Notifier
from tests.support import ADMIN_ID, command


@pytest.fixture
def broken_list(harness):
    harness.paths.whitelist.write_text("{ broken", encoding="utf-8")
    return harness


async def test_failure_is_reported_to_admins(broken_list):
    await broken_list.feed(command("/status"))

    assert "WhitelistCorruptedError" in broken_list.admin_notices()[0]


async def test_repeated_failure_is_reported_once_per_interval(broken_list):
    await broken_list.feed(command("/status"))
    await broken_list.feed(command("/status"))

    assert len(broken_list.admin_notices()) == 1


async def test_failure_is_reported_again_after_the_interval(broken_list, monkeypatch):
    monkeypatch.setattr(notifier_module, "_ALERT_INTERVAL_SECONDS", 0)

    await broken_list.feed(command("/status"))
    await broken_list.feed(command("/status"))

    assert len(broken_list.admin_notices()) == 2


async def test_admin_start_with_a_broken_list_shows_help_and_alerts(broken_list):
    await broken_list.feed(command("/start"))

    help_text, alert = broken_list.admin_notices()
    assert "<code>/add</code>" in help_text
    assert "WhitelistCorruptedError" in alert


async def test_repeated_admin_start_with_a_broken_list_still_gets_an_answer(broken_list):
    await broken_list.feed(command("/start"))
    await broken_list.feed(command("/start"))

    assert sum("<code>/add</code>" in text for text in broken_list.admin_notices()) == 2


async def test_admin_clear_with_a_broken_list_shows_help_and_alerts(broken_list):
    await broken_list.feed(command("/clear", message_id=1))

    help_text, alert = broken_list.admin_notices()
    assert "<code>/add</code>" in help_text
    assert "WhitelistCorruptedError" in alert


async def test_panel_button_with_a_broken_list_stops_spinning_and_alerts(harness):
    await harness.feed(command("/start"))
    harness.paths.whitelist.write_text("{ broken", encoding="utf-8")

    await harness.press("Группы")

    assert harness.last_toast() == "⚠️ Не получилось. Подробности в логе бота."
    assert "WhitelistCorruptedError" in harness.admin_notices()[-1]


async def test_different_failures_are_throttled_separately(harness):
    notifier = Notifier(harness.bot, frozenset({ADMIN_ID}))

    await notifier.alert_admins("first", "one")
    await notifier.alert_admins("second", "two")
    await notifier.alert_admins("first", "one again")

    assert harness.admin_notices() == ["one", "two"]


async def test_undelivered_alert_does_not_use_up_the_interval(harness):
    notifier = Notifier(harness.bot, frozenset({ADMIN_ID}))

    harness.session.failing_methods.add(SendMessage)
    await notifier.alert_admins("first", "lost")
    harness.session.failing_methods.clear()
    await notifier.alert_admins("first", "delivered")

    assert harness.admin_notices()[-1] == "delivered"
