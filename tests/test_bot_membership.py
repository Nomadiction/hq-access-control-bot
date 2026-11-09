import pytest

from tests.support import (
    GROUP_KEY,
    basic_group,
    bot_change,
    channel,
    private_chat,
    supergroup,
)


@pytest.fixture
def alpha(harness):
    harness.given_whitelist({GROUP_KEY: {"project": "Alpha", "members": [{"id": 1}]}})
    return harness


async def test_removed_bot_forgets_the_group(alpha):
    await alpha.feed(bot_change("administrator", "left"))

    assert alpha.whitelist_on_disk() == {}
    assert "Бот удалён" in alpha.admin_notices()[0]
    assert alpha.audit_events() == [f"GROUP-REMOVED {GROUP_KEY} «Alpha»"]


async def test_removal_from_untracked_group_is_silent(alpha):
    await alpha.feed(bot_change("member", "kicked", supergroup(-1009)))

    assert set(alpha.whitelist_on_disk()) == {GROUP_KEY}
    assert alpha.admin_notices() == []


async def test_new_supergroup_is_registered_empty(alpha):
    await alpha.feed(bot_change("left", "administrator", supergroup(-1003, "New")))

    assert alpha.whitelist_on_disk()["-1003"] == {"project": "New", "members": []}
    assert "<code>/add New @username</code>" in alpha.admin_notices()[0]
    assert alpha.audit_events() == ["GROUP-ADDED -1003 «New»"]


async def test_basic_group_gets_a_warning_and_no_registration(alpha):
    await alpha.feed(bot_change("left", "member", basic_group()))

    assert set(alpha.whitelist_on_disk()) == {GROUP_KEY}
    assert "Добавлен в обычную группу" in alpha.admin_notices()[0]


async def test_status_change_inside_basic_group_is_silent(alpha):
    await alpha.feed(bot_change("member", "administrator", basic_group()))

    assert alpha.admin_notices() == []


async def test_promotion_in_tracked_group_is_reported(alpha):
    await alpha.feed(bot_change("member", "administrator"))

    assert "назначен администратором" in alpha.admin_notices()[0]


async def test_demotion_in_tracked_group_is_reported(alpha):
    await alpha.feed(bot_change("administrator", "member"))

    assert "забрали админку" in alpha.admin_notices()[0]


async def test_restricted_bot_changes_nothing(alpha):
    await alpha.feed(bot_change("member", "restricted"))

    assert alpha.admin_notices() == []
    assert set(alpha.whitelist_on_disk()) == {GROUP_KEY}


async def test_restricted_bot_does_not_register_a_new_group(alpha):
    await alpha.feed(bot_change("left", "restricted", supergroup(-1009)))

    assert set(alpha.whitelist_on_disk()) == {GROUP_KEY}


@pytest.mark.parametrize(("old", "new"), [("kicked", "member"), ("member", "kicked")])
async def test_user_blocking_or_unblocking_the_bot_is_not_a_group_event(alpha, old, new):
    await alpha.feed(bot_change(old, new, private_chat(99)))

    assert alpha.admin_notices() == []


async def test_channel_is_not_treated_as_a_group(alpha):
    await alpha.feed(bot_change("left", "administrator", channel()))

    assert alpha.admin_notices() == []
    assert set(alpha.whitelist_on_disk()) == {GROUP_KEY}
