import pytest

from tests.support import (
    GROUP_KEY,
    basic_group,
    bot_change,
    channel,
    command,
    group_renamed,
    private_chat,
    supergroup,
)


@pytest.fixture
def alpha(harness):
    harness.given_whitelist({GROUP_KEY: {"project": "Alpha", "members": [{"id": 1}]}})
    return harness


@pytest.mark.parametrize("status", ["left", "kicked"])
async def test_removed_bot_keeps_the_list_as_inactive(alpha, status):
    await alpha.feed(bot_change("administrator", status))

    assert alpha.whitelist_on_disk()[GROUP_KEY] == {
        "project": "Alpha",
        "members": [{"id": 1}],
        "inactive": True,
    }
    assert "Бот удалён" in alpha.admin_notices()[0]
    assert alpha.audit_events() == [f"GROUP-INACTIVE {GROUP_KEY} «Alpha»"]


async def test_second_removal_event_is_silent(alpha):
    await alpha.feed(bot_change("administrator", "left"))
    await alpha.feed(bot_change("left", "kicked"))

    assert len(alpha.admin_notices()) == 1


async def test_returning_bot_restores_the_list_under_the_current_title(alpha):
    await alpha.feed(bot_change("administrator", "left"))

    await alpha.feed(bot_change("left", "administrator", supergroup(title="Alpha v2")))

    assert alpha.whitelist_on_disk()[GROUP_KEY] == {"project": "Alpha v2", "members": [{"id": 1}]}
    assert "Список доступа восстановлен" in alpha.admin_notices()[1]
    assert alpha.audit_events()[1] == f"GROUP-RESTORED {GROUP_KEY} «Alpha v2»"


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


@pytest.mark.parametrize(
    "update",
    [
        bot_change("left", "member", supergroup(-1003, "New")),
        bot_change("left", "administrator", supergroup(-1003, "New"), can_invite_users=False),
        bot_change("member", "administrator", can_invite_users=False),
        bot_change("administrator", "administrator", can_invite_users=False),
        bot_change("member", "administrator", can_restrict_members=False),
    ],
)
async def test_missing_invite_right_is_reported(alpha, update):
    await alpha.feed(update)

    assert "Не хватает прав" in alpha.admin_notices()[-1]


@pytest.mark.parametrize(
    "update",
    [
        bot_change("left", "administrator", supergroup(-1003, "New")),
        bot_change("member", "administrator"),
        bot_change("administrator", "member"),
    ],
)
async def test_no_rights_warning_when_it_does_not_apply(alpha, update):
    await alpha.feed(update)

    assert not any("Не хватает прав" in notice for notice in alpha.admin_notices())


async def test_group_rename_updates_the_project_name(alpha):
    await alpha.feed(group_renamed("Omega"))

    assert alpha.whitelist_on_disk()[GROUP_KEY]["project"] == "Omega"
    assert "Omega" in alpha.admin_notices()[0]
    assert alpha.audit_events() == [f"GROUP-RENAMED {GROUP_KEY} «Omega»"]

    await alpha.feed(command("/add Omega @xuser"))

    assert alpha.members_on_disk(GROUP_KEY)[1] == {"username": "xuser"}


async def test_rename_to_the_same_title_is_silent(alpha):
    await alpha.feed(group_renamed("Alpha"))

    assert alpha.admin_notices() == []
    assert alpha.audit_events() == []


async def test_rename_of_an_untracked_group_is_ignored(alpha):
    await alpha.feed(group_renamed("Other", supergroup(-1009, "Old")))

    assert set(alpha.whitelist_on_disk()) == {GROUP_KEY}
    assert alpha.admin_notices() == []


async def test_blank_title_falls_back_to_the_chat_id(alpha):
    await alpha.feed(bot_change("left", "administrator", supergroup(-1003, "   ")))

    assert alpha.whitelist_on_disk()["-1003"]["project"] == "-1003"
