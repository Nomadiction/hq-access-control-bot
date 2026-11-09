import pytest

from tests.support import (
    ALICE_RECORD,
    BOT_USER,
    GROUP_KEY,
    make_user,
    member_change,
    supergroup,
)


@pytest.fixture
def alpha(harness):
    harness.given_whitelist(
        {GROUP_KEY: {"project": "Alpha", "members": [ALICE_RECORD, {"username": "pending"}]}}
    )
    return harness


@pytest.mark.parametrize("status", ["left", "kicked"])
async def test_departed_member_loses_entry(alpha, status):
    await alpha.feed(member_change("member", status, make_user(10, "alice", "Alice")))

    assert alpha.members_on_disk(GROUP_KEY) == [{"username": "pending"}]
    assert "Участник вышел" in alpha.admin_notices()[0]
    assert alpha.audit_events() == ["MEMBER-LEFT id=10 project=Alpha @alice"]


async def test_departure_of_unlisted_user_is_silent(alpha):
    await alpha.feed(member_change("member", "left", make_user(99, "bob")))

    assert len(alpha.members_on_disk(GROUP_KEY)) == 2
    assert alpha.admin_notices() == []
    assert alpha.audit_events() == []


@pytest.mark.parametrize("status", ["member", "administrator"])
async def test_present_member_is_bound_and_refreshed(alpha, status):
    await alpha.feed(member_change("left", status, make_user(30, "pending", "Pen")))

    assert alpha.members_on_disk(GROUP_KEY)[1] == {
        "id": 30,
        "username": "pending",
        "in": True,
        "name": "Pen",
    }


async def test_unlisted_user_joining_warns_admins_and_keeps_the_file(alpha):
    before = alpha.paths.whitelist.read_text(encoding="utf-8")

    await alpha.feed(member_change("left", "member", make_user(99, "bob", "Bob")))

    assert alpha.paths.whitelist.read_text(encoding="utf-8") == before
    assert "Вход без доступа" in alpha.admin_notices()[0]
    assert f"/add {GROUP_KEY} 99" in alpha.admin_notices()[0]
    assert alpha.audit_events() == ["MEMBER-UNLISTED id=99 @bob project=Alpha"]


@pytest.mark.parametrize("old", ["member", "administrator"])
async def test_status_change_of_an_unlisted_member_is_silent(alpha, old):
    await alpha.feed(member_change(old, "restricted", make_user(99, "bob")))
    await alpha.feed(member_change("member", "administrator", make_user(98, "carl")))

    assert alpha.admin_notices() == []


async def test_listed_user_joining_is_not_reported_as_unlisted(alpha):
    await alpha.feed(member_change("left", "member", make_user(10, "alice")))

    assert alpha.admin_notices() == []


async def test_user_returning_from_restricted_exit_counts_as_joining(alpha):
    await alpha.feed(member_change("restricted_left", "member", make_user(99, "bob")))

    assert "Вход без доступа" in alpha.admin_notices()[0]


async def test_unlisted_user_entering_with_restrictions_is_reported(alpha):
    await alpha.feed(member_change("left", "restricted", make_user(99, "bob")))

    assert "Вход без доступа" in alpha.admin_notices()[0]


async def test_the_bot_itself_is_never_reported(alpha):
    await alpha.feed(member_change("left", "administrator", BOT_USER))

    assert alpha.admin_notices() == []


async def test_restricted_member_who_left_loses_entry(alpha):
    await alpha.feed(member_change("member", "restricted_left", make_user(10, "alice", "Alice")))

    assert alpha.members_on_disk(GROUP_KEY) == [{"username": "pending"}]


async def test_restricted_member_keeps_entry_unchanged(alpha):
    before = alpha.members_on_disk(GROUP_KEY)

    await alpha.feed(member_change("member", "restricted", make_user(10, "alice", "Alice")))

    assert alpha.members_on_disk(GROUP_KEY) == before


async def test_events_from_untracked_group_do_not_touch_the_file(harness):
    before = harness.paths.whitelist.read_text(encoding="utf-8")

    await harness.feed(member_change("member", "left", make_user(10), supergroup(-1009)))

    assert harness.paths.whitelist.read_text(encoding="utf-8") == before
