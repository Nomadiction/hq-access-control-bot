import pytest

from tests.support import ALICE_RECORD, GROUP_KEY, make_user, member_change, supergroup


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


async def test_unlisted_user_joining_leaves_the_file_untouched(alpha):
    before = alpha.paths.whitelist.read_text(encoding="utf-8")

    await alpha.feed(member_change("left", "member", make_user(99, "bob")))

    assert alpha.paths.whitelist.read_text(encoding="utf-8") == before


async def test_restricted_member_keeps_entry_unchanged(alpha):
    before = alpha.members_on_disk(GROUP_KEY)

    await alpha.feed(member_change("member", "restricted", make_user(10, "alice")))

    assert alpha.members_on_disk(GROUP_KEY) == before


async def test_events_from_untracked_group_do_not_touch_the_file(harness):
    await harness.feed(member_change("member", "left", make_user(10), supergroup(-1009)))

    assert not harness.paths.whitelist.exists()
