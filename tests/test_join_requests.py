import pytest
from aiogram.methods import ApproveChatJoinRequest, DeclineChatJoinRequest, SendMessage

from tests.support import ADMIN_ID, ALICE_RECORD, GROUP_KEY, join_request, make_user, supergroup


@pytest.fixture
def alpha(harness):
    harness.given_whitelist({GROUP_KEY: {"project": "Alpha", "members": [ALICE_RECORD]}})
    return harness


def assert_approved(harness, user_id):
    assert [c.user_id for c in harness.calls_of(ApproveChatJoinRequest)] == [user_id]
    assert harness.calls_of(DeclineChatJoinRequest) == []


def assert_declined(harness, user_id):
    assert [c.user_id for c in harness.calls_of(DeclineChatJoinRequest)] == [user_id]
    assert harness.calls_of(ApproveChatJoinRequest) == []


async def test_member_is_approved_and_everyone_is_told(alpha):
    await alpha.feed(join_request(make_user(10, "alice", "Alice")))

    assert_approved(alpha, 10)
    assert "Добро пожаловать в проект <b>Alpha</b>" in alpha.texts_sent_to(10)[0]
    assert "Заявка одобрена" in alpha.admin_notices()[0]
    assert alpha.audit_events() == ["APPROVED id=10 @alice project=Alpha"]


async def test_stranger_is_declined_and_admin_is_told(alpha):
    await alpha.feed(join_request(make_user(99, "bob", "Bob")))

    assert_declined(alpha, 99)
    assert "Заявка отклонена" in alpha.texts_sent_to(99)[0]
    assert "Bob · @bob" in alpha.admin_notices()[0]
    assert alpha.audit_events() == ["DECLINED id=99 @bob project=Alpha"]


async def test_group_outside_the_whitelist_declines_everyone(alpha):
    await alpha.feed(join_request(make_user(10, "alice"), supergroup(-1009, "Other")))

    assert_declined(alpha, 10)
    assert alpha.audit_events() == ["DECLINED id=10 @alice project=проект"]


async def test_username_entry_gets_bound_to_real_account(harness):
    harness.given_whitelist({GROUP_KEY: {"project": "A", "members": [{"username": "pending"}]}})

    await harness.feed(join_request(make_user(30, "Pending", "Pen")))

    assert_approved(harness, 30)
    assert harness.members_on_disk(GROUP_KEY) == [
        {"id": 30, "username": "pending", "in": True, "name": "Pen"}
    ]


async def test_changed_username_is_recorded(alpha):
    await alpha.feed(join_request(make_user(10, "alice_new", "Alice")))

    assert alpha.members_on_disk(GROUP_KEY)[0]["username"] == "alice_new"


async def test_entering_without_username_keeps_the_last_known_one(harness):
    harness.given_whitelist({GROUP_KEY: {"project": "A", "members": [{"id": 12, "username": "n"}]}})

    await harness.feed(join_request(make_user(12, None, "Nik")))

    assert harness.members_on_disk(GROUP_KEY) == [
        {"id": 12, "username": "n", "in": True, "name": "Nik"}
    ]


async def test_entry_by_id_is_marked_as_joined_on_entry(harness):
    harness.given_whitelist({GROUP_KEY: {"project": "A", "members": [{"id": 12}]}})

    await harness.feed(join_request(make_user(12, None, "Nik")))

    assert harness.members_on_disk(GROUP_KEY) == [{"id": 12, "in": True, "name": "Nik"}]


async def test_binding_merges_username_entry_with_the_id_record(harness):
    harness.given_whitelist(
        {GROUP_KEY: {"project": "A", "members": [{"username": "nik"}, {"id": 12}]}}
    )

    await harness.feed(join_request(make_user(12, "nik", "Nik")))

    assert harness.members_on_disk(GROUP_KEY) == [
        {"id": 12, "username": "nik", "in": True, "name": "Nik"}
    ]


async def test_taken_over_username_does_not_grant_access(alpha):
    await alpha.feed(join_request(make_user(66, "alice", "Thief")))

    assert_declined(alpha, 66)
    assert alpha.members_on_disk(GROUP_KEY) == [ALICE_RECORD]


async def test_binding_an_entry_keeps_member_with_stale_same_username(harness):
    stale = {"id": 1, "username": "foo", "in": True}
    harness.given_whitelist({GROUP_KEY: {"project": "A", "members": [stale, {"username": "foo"}]}})

    await harness.feed(join_request(make_user(2, "foo", "New")))

    assert harness.members_on_disk(GROUP_KEY) == [
        stale,
        {"id": 2, "username": "foo", "in": True, "name": "New"},
    ]


async def test_user_supplied_name_is_escaped_in_notices(alpha):
    await alpha.feed(join_request(make_user(77, None, "<b>&x")))

    assert "&lt;b&gt;&amp;x · <i>без username</i>" in alpha.admin_notices()[0]


async def test_undeliverable_dm_does_not_stop_processing(alpha):
    alpha.session.failing_methods.add(SendMessage)

    await alpha.feed(join_request(make_user(99, "bob")))

    assert_declined(alpha, 99)
    assert alpha.audit_events() == ["DECLINED id=99 @bob project=Alpha"]
    assert [call.chat_id for call in alpha.calls_of(SendMessage)] == [99, ADMIN_ID]


async def test_failed_approval_is_not_audited(alpha):
    alpha.session.failing_methods.add(ApproveChatJoinRequest)

    await alpha.feed(join_request(make_user(10, "alice")))

    assert alpha.audit_events() == []
    assert alpha.admin_notices() == []


async def test_corrupted_whitelist_grants_nothing(harness):
    harness.paths.whitelist.write_text("{ broken", encoding="utf-8")

    await harness.feed(join_request(make_user(10, "alice")))

    assert harness.calls_of(ApproveChatJoinRequest) == []
    assert harness.paths.whitelist.read_text(encoding="utf-8") == "{ broken"
