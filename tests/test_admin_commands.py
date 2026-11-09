import pytest
from aiogram.methods import GetChatMember, SendMessage

from hq_access_bot.handlers.command_args import parse_target_and_members
from hq_access_bot.whitelist.identity import MemberRef
from hq_access_bot.whitelist.models import Group, Whitelist
from tests.support import (
    ALICE_RECORD,
    GROUP_KEY,
    STRANGER,
    TELEGRAM_MESSAGE_LIMIT,
    command,
    count_utf16_units,
    supergroup,
)

SECOND_KEY = "-1002"
KNOWN_PROJECTS = Whitelist(
    {
        "-1": Group("Alpha"),
        "-2": Group("Beta Two"),
        "-3": Group("Test"),
        "-4": Group("Test 2"),
        "-5": Group("Release 3"),
    }
)


@pytest.fixture
def groups(harness):
    harness.given_whitelist(
        {
            GROUP_KEY: {
                "project": "Alpha",
                "members": [
                    ALICE_RECORD,
                    {"username": "pending"},
                ],
            },
            SECOND_KEY: {"project": "Beta Two", "members": [{"id": 20, "in": True, "name": "Nik"}]},
        }
    )
    return harness


@pytest.mark.parametrize(
    ("args", "expected_target", "expected_refs"),
    [
        (None, "", []),
        ("Alpha", "Alpha", []),
        ("Alpha @Anna 5", "Alpha", [MemberRef(username="anna"), MemberRef(user_id=5)]),
        ("Beta Two @anna", "Beta Two", [MemberRef(username="anna")]),
        ("-100123 7", "-100123", [MemberRef(user_id=7)]),
        ("Test 7", "Test", [MemberRef(user_id=7)]),
        ("Test 2 @anna", "Test 2", [MemberRef(username="anna")]),
        ("Test 2 7", "Test 2", [MemberRef(user_id=7)]),
        ("Test 2", "Test 2", []),
        ("Release 3 8 9", "Release 3", [MemberRef(user_id=8), MemberRef(user_id=9)]),
        ("Unknown 3 @anna", "Unknown", [MemberRef(user_id=3), MemberRef(username="anna")]),
        ("Alpha @anna, @petr", "Alpha", [MemberRef(username="anna"), MemberRef(username="petr")]),
        ("Alpha @anna , 5", "Alpha", [MemberRef(username="anna"), MemberRef(user_id=5)]),
        (
            "Alpha @anna,@petr,5",
            "Alpha",
            [MemberRef(username="anna"), MemberRef(username="petr"), MemberRef(user_id=5)],
        ),
        ("Alpha ²", "Alpha ²", []),
        ("Test 2, @anna", "Test 2", [MemberRef(username="anna")]),
        ("Unknown 3, @anna", "Unknown", [MemberRef(user_id=3), MemberRef(username="anna")]),
    ],
)
def test_parse_target_and_members(args, expected_target, expected_refs):
    parsed = parse_target_and_members(args, KNOWN_PROJECTS)

    assert (parsed.target, parsed.refs, parsed.invalid) == (expected_target, expected_refs, [])


@pytest.mark.parametrize("bad_username", ["@", "@a!b", "@abc", "@1abcd", "@" + "a" * 33, "@анна"])
def test_parse_reports_invalid_usernames(bad_username):
    parsed = parse_target_and_members(f"Alpha @anna {bad_username}", KNOWN_PROJECTS)

    assert parsed.target == "Alpha"
    assert parsed.refs == [MemberRef(username="anna")]
    assert parsed.invalid == [bad_username]


@pytest.mark.parametrize("good_username", ["@abcd", "@" + "a" * 32, "@a_1b"])
def test_parse_accepts_valid_usernames(good_username):
    assert parse_target_and_members(f"Alpha {good_username}", KNOWN_PROJECTS).invalid == []


@pytest.mark.parametrize(
    "text", ["/status", "/add Alpha @xuser", "/remove Alpha @alice", "/reload"]
)
async def test_admin_commands_are_ignored_for_strangers(groups, text):
    before = groups.whitelist_on_disk()

    await groups.feed(command(text, STRANGER))

    assert groups.calls_of(SendMessage) == []
    assert groups.whitelist_on_disk() == before


async def test_admin_commands_are_ignored_in_groups(groups):
    await groups.feed(command("/status", chat=supergroup()))

    assert groups.calls_of(SendMessage) == []


async def test_status_counts_groups_and_unique_members(groups):
    await groups.feed(command("/status"))

    report = groups.admin_notices()[0]
    assert "Аптайм: <b>0 ч 0 мин</b>" in report
    assert "Групп: <b>2</b> · Участников: <b>3</b>" in report


async def test_add_reports_new_and_existing_members(groups):
    await groups.feed(command("/add Alpha @Newbie 555 @alice 10"))

    usernames_and_ids = [
        (m.get("id"), m.get("username")) for m in groups.members_on_disk(GROUP_KEY)
    ]
    assert usernames_and_ids[2:] == [(None, "newbie"), (555, None)]
    assert "✅ Добавлено: @newbie, id 555" in groups.admin_notices()[0]
    assert "⏭ Уже были: @alice, id 10" in groups.admin_notices()[0]
    assert groups.audit_events() == ["ADD project=Alpha @newbie, id 555"]


@pytest.mark.parametrize("text", ["/add Alpha @a!b @xuser", "/remove Alpha @a!b"])
async def test_invalid_username_rejects_the_whole_command(groups, text):
    before = groups.whitelist_on_disk()

    await groups.feed(command(text))

    assert groups.whitelist_on_disk() == before
    assert "Некорректные ники" in groups.admin_notices()[0]
    assert "a!b" in groups.admin_notices()[0]


async def test_add_accepts_multi_word_project_in_any_case(groups):
    await groups.feed(command("/add beta two @xuser"))

    assert groups.members_on_disk(SECOND_KEY)[1] == {"username": "xuser"}


async def test_add_targets_a_project_whose_name_ends_in_a_number(harness):
    harness.given_whitelist({GROUP_KEY: {"project": "Test 2", "members": []}})

    await harness.feed(command("/add Test 2 @xuser"))

    assert harness.members_on_disk(GROUP_KEY) == [{"username": "xuser"}]


async def test_add_with_only_existing_members_writes_no_audit(groups):
    await groups.feed(command("/add Alpha @alice"))

    assert groups.audit_events() == []


@pytest.mark.parametrize(
    "text",
    ["/add Nope @xuser", "/remove Nope @xuser", "/delgroup Nope"],
)
async def test_unknown_group_is_reported(groups, text):
    await groups.feed(command(text))

    assert groups.admin_notices() == ["Не нашёл группу: <b>Nope</b>"]


@pytest.fixture
def twin_groups(harness):
    harness.given_whitelist(
        {
            GROUP_KEY: {"project": "Team", "members": [{"username": "first"}]},
            SECOND_KEY: {"project": "team", "members": []},
        }
    )
    return harness


@pytest.mark.parametrize("text", ["/add Team @xuser", "/remove Team @first", "/delgroup Team"])
async def test_ambiguous_project_name_changes_nothing_and_lists_the_groups(twin_groups, text):
    before = twin_groups.whitelist_on_disk()

    await twin_groups.feed(command(text))

    assert twin_groups.whitelist_on_disk() == before
    assert GROUP_KEY in twin_groups.admin_notices()[0]
    assert SECOND_KEY in twin_groups.admin_notices()[0]


async def test_ambiguous_reply_shows_which_group_is_inactive(harness):
    harness.given_whitelist(
        {
            GROUP_KEY: {"project": "Team", "members": [], "inactive": True},
            SECOND_KEY: {"project": "Team", "members": []},
        }
    )

    await harness.feed(command("/delgroup Team"))

    assert "<b>Team</b> <i>(бот не в группе)</i>" in harness.admin_notices()[0]


async def test_chat_id_selects_one_of_the_twin_groups(twin_groups):
    await twin_groups.feed(command(f"/add {SECOND_KEY} @xuser"))

    assert twin_groups.members_on_disk(SECOND_KEY) == [{"username": "xuser"}]
    assert twin_groups.members_on_disk(GROUP_KEY) == [{"username": "first"}]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/add", "/add &lt;проект&gt;"),
        ("/add Alpha", "/add &lt;проект&gt;"),
        ("/remove", "/remove &lt;проект&gt;"),
        ("/delgroup", "/delgroup &lt;проект"),
    ],
)
async def test_missing_arguments_show_usage(groups, text, expected):
    await groups.feed(command(text))

    assert expected in groups.admin_notices()[0]


async def test_remove_by_username_and_id(groups):
    await groups.feed(command("/remove Alpha @alice @pending"))

    assert groups.members_on_disk(GROUP_KEY) == []
    assert "🗑 Удалено: @alice, @pending" in groups.admin_notices()[0]
    assert groups.audit_events() == ["REMOVE project=Alpha @alice, @pending"]


async def test_remove_by_id_labels_member_without_username(groups):
    await groups.feed(command("/remove beta two 20"))

    assert "🗑 Удалено: id 20" in groups.admin_notices()[0]


async def test_remove_targets_a_project_whose_name_ends_in_a_number(harness):
    harness.given_whitelist({GROUP_KEY: {"project": "Test 2", "members": [{"username": "xuser"}]}})

    await harness.feed(command("/remove Test 2 @xuser"))

    assert harness.members_on_disk(GROUP_KEY) == []


async def test_remove_nobody_is_reported_and_not_audited(groups):
    await groups.feed(command("/remove Alpha @ghost"))

    assert "Никого не нашёл" in groups.admin_notices()[0]
    assert groups.audit_events() == []


async def test_delgroup_by_project_name(groups):
    await groups.feed(command("/delgroup Beta Two"))

    assert set(groups.whitelist_on_disk()) == {GROUP_KEY}
    assert groups.audit_events() == [f"GROUP-DELETED {SECOND_KEY} «Beta Two» (manual)"]


async def test_delgroup_by_chat_id(groups):
    await groups.feed(command(f"/delgroup {GROUP_KEY}"))

    assert set(groups.whitelist_on_disk()) == {SECOND_KEY}


async def test_reload_on_empty_whitelist(harness):
    await harness.feed(command("/reload"))

    assert harness.admin_notices() == ["Список доступа пуст."]


async def test_reload_syncs_with_telegram_and_lists_members(groups):
    groups.session.chat_members = {10: ("left", "alice"), 20: ("member", "fresh")}

    await groups.feed(command("/reload"))

    assert groups.members_on_disk(GROUP_KEY) == [{"username": "pending"}]
    assert groups.members_on_disk(SECOND_KEY)[0]["username"] == "fresh"
    report = groups.admin_notices()[0]
    assert "@pending <i>· ожидает входа</i>" in report
    assert "@fresh <tg-spoiler>20</tg-spoiler>" in report


async def test_reload_removes_restricted_member_who_left(groups):
    groups.session.chat_members = {10: ("restricted_left", "alice")}

    await groups.feed(command("/reload"))

    assert groups.members_on_disk(GROUP_KEY) == [{"username": "pending"}]


async def test_reload_keeps_a_member_who_joined_during_the_check(harness, monkeypatch):
    awaiting = {"id": 30, "username": "newbie"}
    harness.given_whitelist({GROUP_KEY: {"project": "A", "members": [awaiting]}})
    harness.session.chat_members = {30: ("left", "newbie")}
    answer_from_telegram = harness.session._build_chat_member

    def join_while_telegram_answers(method):
        joined = {**awaiting, "in": True}
        harness.given_whitelist({GROUP_KEY: {"project": "A", "members": [joined]}})
        return answer_from_telegram(method)

    monkeypatch.setattr(harness.session, "_build_chat_member", join_while_telegram_answers)

    await harness.feed(command("/reload"))

    assert harness.members_on_disk(GROUP_KEY) == [{**awaiting, "in": True}]


async def test_reload_does_not_poll_inactive_groups_and_marks_them(harness):
    harness.given_whitelist(
        {GROUP_KEY: {"project": "A", "members": [{"id": 1, "in": True}], "inactive": True}}
    )

    await harness.feed(command("/reload"))

    assert harness.calls_of(GetChatMember) == []
    assert harness.members_on_disk(GROUP_KEY) == [{"id": 1, "in": True}]
    assert "<b>A</b> <i>(бот не в группе)</i>" in harness.admin_notices()[0]


async def test_inactive_group_can_still_be_edited_and_finally_deleted(harness):
    harness.given_whitelist({GROUP_KEY: {"project": "A", "members": [], "inactive": True}})

    await harness.feed(command("/add A @xuser"))
    assert harness.members_on_disk(GROUP_KEY) == [{"username": "xuser"}]

    await harness.feed(command("/delgroup A"))
    assert harness.whitelist_on_disk() == {}


async def test_reload_splits_a_long_list_within_the_telegram_limit(harness):
    members = [{"id": n, "username": f"user_{n:05d}", "in": True} for n in range(1, 400)]
    harness.given_whitelist({GROUP_KEY: {"project": "A", "members": members}})

    await harness.feed(command("/reload"))

    messages = harness.admin_notices()
    assert len(messages) > 1
    assert all(count_utf16_units(message) <= TELEGRAM_MESSAGE_LIMIT for message in messages)
    combined = "\n".join(messages)
    assert all(f"@user_{n:05d}" in combined for n in range(1, 400))


async def test_reload_limit_counts_characters_outside_the_basic_plane(harness):
    wide_name = "𝕍" * 40
    members = [{"id": n, "name": wide_name, "in": True} for n in range(1, 200)]
    harness.given_whitelist({GROUP_KEY: {"project": "A", "members": members}})

    await harness.feed(command("/reload"))

    assert all(count_utf16_units(m) <= TELEGRAM_MESSAGE_LIMIT for m in harness.admin_notices())


async def test_reload_keeps_a_short_list_in_one_message(groups):
    await groups.feed(command("/reload"))

    assert len(groups.admin_notices()) == 1


async def test_reload_keeps_members_telegram_could_not_confirm(groups):
    await groups.feed(command("/reload"))

    assert len(groups.members_on_disk(GROUP_KEY)) == 2


async def test_reload_labels_members_without_username_and_empty_groups(harness):
    harness.given_whitelist(
        {
            GROUP_KEY: {"project": "A", "members": [{"id": 1, "name": "Nik"}, {"id": 2}]},
            SECOND_KEY: {"project": "B", "members": []},
        }
    )

    await harness.feed(command("/reload"))

    report = harness.admin_notices()[0]
    assert "Nik <i>(без @username)</i>" in report
    assert "<i>без имени</i>" in report
    assert "<b>B</b>\n<i>пусто</i>" in report


async def test_replies_about_long_input_fit_the_telegram_limit(groups):
    await groups.feed(command("/add Alpha " + " ".join(str(1000 + i) for i in range(500))))
    await groups.feed(command("/add Alpha " + " ".join(["@&&&"] * 900)))

    assert all(count_utf16_units(text) <= TELEGRAM_MESSAGE_LIMIT for text in groups.admin_notices())
    assert "и ещё" in groups.admin_notices()[0]
