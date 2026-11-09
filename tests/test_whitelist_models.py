import pytest

from hq_access_bot.whitelist.identity import (
    MemberRef,
    ObservedMember,
    Person,
    normalize_username,
)
from hq_access_bot.whitelist.models import Group, Member, Whitelist


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("@Alice", "alice"), ("alice", "alice"), ("", None), ("@", None), (None, None)],
)
def test_normalize_username(raw, expected):
    assert normalize_username(raw) == expected


@pytest.mark.parametrize(
    ("member", "ref", "expected"),
    [
        (Member(user_id=1), MemberRef(user_id=1), True),
        (Member(user_id=1), MemberRef(user_id=2), False),
        (Member(username="a"), MemberRef(user_id=2, username="a"), True),
        (Member(username="a"), MemberRef(user_id=2, username="b"), False),
        (Member(user_id=1, username="a"), MemberRef(user_id=2, username="a"), False),
        (Member(user_id=1, username="a"), MemberRef(username="a"), True),
        (Member(username="a"), MemberRef(user_id=2), False),
        (Member(user_id=1), MemberRef(), False),
    ],
)
def test_member_matching(member, ref, expected):
    assert member.matches(ref) is expected


def observed(user_id, username=None, *, in_group=True, name="Seen"):
    return ObservedMember(Person(user_id, username, name), in_group)


def test_reconcile_refreshes_member_found_in_group():
    group = Group("A", [Member(user_id=1, username="old")])

    group.reconcile({1: observed(1, "New", name="Fresh")})

    assert list(group.members) == [
        Member(user_id=1, username="new", has_joined=True, full_name="Fresh")
    ]


def test_reconcile_clears_username_the_member_no_longer_has():
    group = Group("A", [Member(user_id=1, username="old", has_joined=True)])

    group.reconcile({1: observed(1, None)})

    assert group.members[0].username is None


def test_reconcile_removes_member_who_left():
    group = Group("A", [Member(user_id=1, has_joined=True)])

    group.reconcile({1: observed(1, in_group=False)})

    assert list(group.members) == []


def test_reconcile_keeps_entry_not_used_yet():
    entry = Member(user_id=1)
    group = Group("A", [entry])

    group.reconcile({1: observed(1, in_group=False)})

    assert list(group.members) == [entry]


def test_reconcile_keeps_member_it_could_not_check():
    member = Member(user_id=1, has_joined=True)
    group = Group("A", [member])

    group.reconcile({})

    assert list(group.members) == [member]


@pytest.mark.parametrize("twin_source", ["current", "stored"])
def test_reconcile_drops_username_twin_of_departed_member(twin_source):
    stored_username = "twin" if twin_source == "stored" else None
    observed_username = "twin" if twin_source == "current" else None
    group = Group(
        "A",
        [
            Member(user_id=1, username=stored_username, has_joined=True),
            Member(username="twin"),
            Member(username="other"),
        ],
    )

    group.reconcile({1: observed(1, observed_username, in_group=False)})

    assert list(group.members) == [Member(username="other")]


def test_reconcile_merges_username_twin_into_member_with_id():
    group = Group("A", [Member(user_id=1, has_joined=True), Member(username="twin")])

    group.reconcile({1: observed(1, "twin")})

    assert [m.user_id for m in group.members] == [1]


def test_remove_all_reports_removed_and_unmatched_references():
    group = Group("A", [Member(user_id=1, username="a")])

    change = group.remove_all([MemberRef(username="a"), MemberRef(username="ghost")])

    assert (change.applied, change.skipped) == (["@a"], ["@ghost"])
    assert group.members == ()


def test_find_group_key_prefers_exact_chat_id_then_project_name():
    whitelist = Whitelist({"-100": Group("Alpha Team"), "-200": Group("-100")})

    assert whitelist.find_group_key("-100") == "-100"
    assert whitelist.find_group_key("alpha TEAM") == "-100"
    assert whitelist.find_group_key("nope") is None


def test_count_unique_members_counts_each_identity_once():
    whitelist = Whitelist(
        {
            "-1": Group("A", [Member(user_id=1, username="a"), Member(username="b")]),
            "-2": Group("B", [Member(user_id=1), Member(username="b"), Member(username="c")]),
        }
    )

    assert whitelist.count_unique_members() == 3
