import asyncio

import pytest
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteMessage,
    DeleteMessages,
    EditMessageText,
    GetChatMember,
    SendMessage,
)

from hq_access_bot.handlers import access_list_changes
from hq_access_bot.whitelist.store import WhitelistStore
from tests.support import (
    ADMIN_ID,
    ALICE_RECORD,
    FIRST_SENT_MESSAGE_ID,
    GROUP_KEY,
    PANEL_MESSAGE_ID,
    STRANGER,
    TELEGRAM_MESSAGE_LIMIT,
    bad_request,
    button_press,
    command,
    count_utf16_units,
    network_failure,
    retry_after,
    supergroup,
)

SYNC_LABEL = "🔄 Сверить с Telegram"


@pytest.fixture
def panel(harness):
    harness.given_whitelist(
        {GROUP_KEY: {"project": "Alpha", "members": [ALICE_RECORD, {"username": "pending"}]}}
    )
    return harness


async def open_card(harness, project="Alpha"):
    await harness.open_groups()
    await harness.press(project)


async def start_adding(harness):
    await open_card(harness)
    await harness.press("Добавить")


def member_names(harness, chat_key=GROUP_KEY):
    return [m.get("username") or m["id"] for m in harness.members_on_disk(chat_key)]


async def test_add_button_asks_for_members(panel):
    await start_adding(panel)

    prompt = panel.current_screen().text
    assert "<b>Alpha</b>" in prompt
    assert "Пришлите ники или ID" in prompt
    assert panel.screen_labels() == ["Отмена"]


async def test_sent_members_are_added_and_shown_in_the_panel(panel):
    await start_adding(panel)

    await panel.feed(command("@newbie, 777"))

    assert member_names(panel) == ["alice", "pending", "newbie", 777]
    assert "ADD project=Alpha @newbie, id 777" in panel.audit_events()
    result = panel.calls_of(EditMessageText)[-1]
    assert result.message_id == PANEL_MESSAGE_ID
    assert result.text.endswith("✅ Добавлено: @newbie, id 777")
    assert panel.screen_labels() == ["➕ Ещё", "← К группе"]


async def test_admins_message_with_members_is_deleted(panel):
    await start_adding(panel)

    await panel.feed(command("@newbie", message_id=44))

    assert [call.message_id for call in panel.calls_of(DeleteMessage)] == [44]


async def test_undeletable_message_does_not_stop_the_addition(panel):
    panel.session.failing_methods.add(DeleteMessage)
    await start_adding(panel)

    await panel.feed(command("@newbie"))

    assert "newbie" in member_names(panel)
    assert "✅ Добавлено: @newbie" in panel.current_screen().text
    assert panel.no_failure_alert()


async def test_already_listed_members_are_reported(panel):
    await start_adding(panel)

    await panel.feed(command("@alice"))

    assert "⏭ Уже были: @alice" in panel.current_screen().text


async def test_only_one_message_is_taken_as_members(panel):
    await start_adding(panel)
    await panel.feed(command("@newbie"))

    await panel.feed(command("@another"))

    assert "another" not in member_names(panel)


async def test_invalid_username_adds_nobody_and_keeps_asking(panel):
    await start_adding(panel)

    await panel.feed(command("@good_name @bad-name"))

    assert member_names(panel) == ["alice", "pending"]
    assert "Некорректные ники" in panel.current_screen().text
    assert "Пришлите ники или ID" in panel.current_screen().text

    await panel.feed(command("@good_name"))

    assert "good_name" in member_names(panel)


async def test_error_about_a_huge_message_fits_the_telegram_limit(panel):
    await start_adding(panel)

    await panel.feed(command("&" * 3900 + " " + " ".join(["&&&"] * 30)))

    assert count_utf16_units(panel.current_screen().text) <= TELEGRAM_MESSAGE_LIMIT


async def test_message_without_members_keeps_asking(panel):
    await start_adding(panel)

    await panel.feed(command(",,,"))

    assert "хотя бы один" in panel.current_screen().text
    assert panel.screen_labels() == ["Отмена"]


async def test_long_list_is_added_in_full_with_a_shortened_report(panel):
    await start_adding(panel)

    await panel.feed(command(" ".join(str(1000 + i) for i in range(101))))

    assert len(member_names(panel)) == 103
    assert "и ещё 61" in panel.current_screen().text


async def test_the_largest_allowed_report_fits_the_telegram_limit(panel):
    await start_adding(panel)

    await panel.feed(command(" ".join(f"@u{i:03}" + "a" * 28 for i in range(100))))

    assert "✅ Добавлено" in panel.current_screen().text
    assert count_utf16_units(panel.current_screen().text) <= TELEGRAM_MESSAGE_LIMIT


async def test_command_during_input_is_a_command(panel):
    await start_adding(panel)

    await panel.feed(command("/status"))

    assert member_names(panel) == ["alice", "pending"]
    assert "Статус бота" in panel.current_screen().text

    await panel.feed(command("@newbie"))

    assert "newbie" in member_names(panel)


async def test_cancel_returns_to_the_card_and_ends_the_input(panel):
    await start_adding(panel)

    await panel.press("Отмена")

    assert "Участников: <b>2</b>" in panel.current_screen().text
    await panel.feed(command("@newbie"))
    assert "newbie" not in member_names(panel)


async def test_start_ends_the_input(panel):
    await start_adding(panel)

    await panel.feed(command("/start"))
    await panel.feed(command("@newbie"))

    assert "newbie" not in member_names(panel)


async def test_clear_ends_the_input(panel):
    await start_adding(panel)

    await panel.feed(command("/clear", message_id=1))
    await panel.feed(command("@newbie"))

    assert "newbie" not in member_names(panel)


async def test_text_of_another_user_is_not_taken_as_members(panel):
    await start_adding(panel)

    await panel.feed(command("@newbie", STRANGER))

    assert "newbie" not in member_names(panel)
    assert panel.calls_of(DeleteMessage) == []
    assert panel.no_failure_alert()


async def test_text_in_a_group_is_not_taken_as_members(panel):
    await start_adding(panel)

    await panel.feed(command("@newbie", chat=supergroup()))

    assert "newbie" not in member_names(panel)
    assert panel.calls_of(DeleteMessage) == []


async def test_group_deleted_during_input_is_explained(panel):
    await start_adding(panel)
    panel.given_whitelist({"-1009": {"project": "Other", "members": []}})

    await panel.feed(command("@newbie"))

    assert "Этой группы уже нет в списке." in panel.current_screen().text
    assert "Other · 0" in panel.screen_labels()
    deletes_before = len(panel.calls_of(DeleteMessage))
    await panel.feed(command("@another"))
    assert panel.members_on_disk("-1009") == []
    assert len(panel.calls_of(DeleteMessage)) == deletes_before


async def test_result_is_sent_as_a_new_message_when_the_panel_is_gone(panel):
    await start_adding(panel)
    panel.session.script_errors(EditMessageText, bad_request("Bad Request: message not found"))

    await panel.feed(command("@newbie"))

    assert "✅ Добавлено: @newbie" in panel.calls_of(SendMessage)[-1].text
    assert panel.no_failure_alert()


async def test_repeating_the_same_error_is_not_a_failure(panel):
    await start_adding(panel)
    await panel.feed(command("@bad-name"))
    panel.session.script_errors(
        EditMessageText, bad_request("Bad Request: message is not modified: same content")
    )
    messages_before = len(panel.calls_of(SendMessage))

    await panel.feed(command("@bad-name"))

    assert len(panel.calls_of(SendMessage)) == messages_before


async def test_more_button_asks_again(panel):
    await start_adding(panel)
    await panel.feed(command("@newbie"))

    await panel.press("Ещё")
    await panel.feed(command("@another"))

    assert member_names(panel)[-2:] == ["newbie", "another"]


async def test_add_button_of_a_deleted_group_does_not_start_input(panel):
    await open_card(panel)
    add_button = panel.screen_button("Добавить")
    panel.given_whitelist({})

    await panel.feed(button_press(add_button.callback_data))
    await panel.feed(command("@newbie"))

    assert panel.last_toast() == "Этой группы уже нет в списке."
    assert panel.whitelist_on_disk() == {}
    assert panel.calls_of(DeleteMessage) == []


async def test_any_panel_button_ends_the_input(panel):
    await panel.feed(command("/start"))
    home_button = panel.screen_button("Статус")
    await start_adding(panel)
    await panel.feed(button_press(home_button.callback_data))

    await panel.feed(command("@newbie"))

    assert "newbie" not in member_names(panel)


async def test_remove_screen_lists_members_as_buttons(panel):
    await open_card(panel)

    await panel.press("Убрать")

    assert panel.screen_labels() == ["❌ @alice", "❌ @pending", "← Назад"]
    assert [len(row) for row in panel.current_screen().reply_markup.inline_keyboard] == [1, 1, 1]


async def test_remove_screen_names_members_without_username(harness):
    members = [{"id": 5, "in": True, "name": "Иван"}, {"id": 6}]
    harness.given_whitelist({GROUP_KEY: {"project": "Alpha", "members": members}})
    await open_card(harness)

    await harness.press("Убрать")

    assert harness.screen_labels()[:2] == ["❌ Иван", "❌ id 6"]


async def test_pressing_a_member_removes_only_that_member(panel):
    await open_card(panel)
    await panel.press("Убрать")

    await panel.press("@pending")

    assert member_names(panel) == ["alice"]
    assert "REMOVE project=Alpha @pending" in panel.audit_events()
    assert panel.last_toast() == "Убран: @pending"
    assert panel.screen_labels() == ["❌ @alice", "← Назад"]


async def test_member_already_removed_is_explained(panel):
    await open_card(panel)
    await panel.press("Убрать")
    alice = panel.screen_button("@alice")
    await panel.feed(button_press(alice.callback_data))

    await panel.feed(button_press(alice.callback_data))

    assert panel.last_toast() == "Этого участника уже нет в списке."
    assert sum("REMOVE" in event for event in panel.audit_events()) == 1


async def test_member_with_an_unusual_username_can_be_removed(harness):
    odd_name = "odd:name" + "x" * 80
    harness.given_whitelist({GROUP_KEY: {"project": "Alpha", "members": [{"username": odd_name}]}})
    await open_card(harness)
    await harness.press("Убрать")

    await harness.press("odd:name")

    assert harness.members_on_disk(GROUP_KEY) == []


async def test_remove_screen_says_when_nobody_is_left(harness):
    harness.given_whitelist({GROUP_KEY: {"project": "Alpha", "members": []}})
    await open_card(harness)

    await harness.press("Убрать")

    assert "Убирать некого" in harness.current_screen().text
    assert harness.screen_labels() == ["← Назад"]


async def test_back_from_remove_screen_returns_to_the_card(panel):
    await open_card(panel)
    await panel.press("Убрать")

    await panel.press("Назад")

    assert "Участников: <b>2</b>" in panel.current_screen().text


@pytest.fixture
def crowded(harness):
    members = [{"username": f"user_{i:03}"} for i in range(11)]
    harness.given_whitelist({GROUP_KEY: {"project": "Alpha", "members": members}})
    return harness


async def test_remove_screen_is_split_into_pages(crowded):
    await open_card(crowded)
    await crowded.press("Убрать")

    assert len(crowded.screen_labels()) == 10 + 2
    assert "Стр. 1 из 2" in crowded.current_screen().text

    await crowded.press("▶️")

    assert crowded.screen_labels() == ["❌ @user_010", "◀️", "← Назад"]


async def test_removing_the_last_member_of_a_page_shows_the_previous_page(crowded):
    await open_card(crowded)
    await crowded.press("Убрать")
    await crowded.press("▶️")

    await crowded.press("@user_010")

    assert "❌ @user_009" in crowded.screen_labels()


async def test_removing_a_member_stays_on_the_same_page(harness):
    members = [{"username": f"user_{i:03}"} for i in range(12)]
    harness.given_whitelist({GROUP_KEY: {"project": "Alpha", "members": members}})
    await open_card(harness)
    await harness.press("Убрать")
    await harness.press("▶️")

    await harness.press("@user_010")

    assert harness.screen_labels() == ["❌ @user_011", "◀️", "← Назад"]


@pytest.mark.parametrize(
    ("open_screen", "leave_screen"),
    [("Убрать", "Назад"), ("Добавить", "Отмена"), ("Удалить группу", "Отмена")],
)
async def test_card_actions_return_to_the_page_of_the_group_list(
    many_groups, open_screen, leave_screen
):
    await many_groups.open_groups()
    await many_groups.press("▶️")
    await many_groups.press("Group 11")
    await many_groups.press(open_screen)
    await many_groups.press(leave_screen)

    await many_groups.press("Назад")

    assert "Group 10 · 0" in many_groups.screen_labels()


async def test_add_result_returns_to_the_page_of_the_group_list(many_groups):
    await many_groups.open_groups()
    await many_groups.press("▶️")
    await many_groups.press("Group 11")
    await many_groups.press("Добавить")
    await many_groups.feed(command("@newbie"))
    await many_groups.press("К группе")

    await many_groups.press("Назад")

    assert "Group 10 · 0" in many_groups.screen_labels()


async def test_previous_page_of_remove_screen(crowded):
    await open_card(crowded)
    await crowded.press("Убрать")
    await crowded.press("▶️")

    await crowded.press("◀️")

    assert "❌ @user_000" in crowded.screen_labels()


async def test_remove_button_of_a_deleted_group_is_explained(panel):
    await open_card(panel)
    await panel.press("Убрать")
    alice = panel.screen_button("@alice")
    panel.given_whitelist({})

    await panel.feed(button_press(alice.callback_data))

    assert panel.last_toast() == "Этой группы уже нет в списке."
    assert not any("REMOVE" in event for event in panel.audit_events())


async def test_delete_button_only_asks_for_confirmation(panel):
    await open_card(panel)

    await panel.press("Удалить группу")

    assert GROUP_KEY in panel.whitelist_on_disk()
    assert "Вернуть список будет нельзя" in panel.current_screen().text
    assert panel.screen_labels() == ["Да, удалить", "Отмена"]
    assert panel.screen_button("Да, удалить").style == "danger"


async def test_confirmed_deletion_removes_the_group(panel):
    await open_card(panel)
    await panel.press("Удалить группу")

    await panel.press("Да, удалить")

    assert panel.whitelist_on_disk() == {}
    assert f"GROUP-DELETED {GROUP_KEY} «Alpha» (manual)" in panel.audit_events()
    assert panel.last_toast() == "Группа удалена."


async def test_cancelled_deletion_returns_to_the_card(panel):
    await open_card(panel)
    await panel.press("Удалить группу")

    await panel.press("Отмена")

    assert GROUP_KEY in panel.whitelist_on_disk()
    assert "Участников: <b>2</b>" in panel.current_screen().text


async def test_confirming_twice_deletes_once(panel):
    await open_card(panel)
    await panel.press("Удалить группу")
    confirm = panel.screen_button("Да, удалить")
    await panel.feed(button_press(confirm.callback_data))

    await panel.feed(button_press(confirm.callback_data))

    assert panel.last_toast() == "Этой группы уже нет в списке."
    assert sum("GROUP-DELETED" in event for event in panel.audit_events()) == 1


async def test_deletion_of_a_listed_group_stays_on_its_page(many_groups):
    await many_groups.open_groups()
    await many_groups.press("▶️")
    await many_groups.press("Group 11")
    await many_groups.press("Удалить группу")

    await many_groups.press("Да, удалить")

    assert "Group 10 · 0" in many_groups.screen_labels()


async def test_action_buttons_do_nothing_for_a_non_admin(panel):
    await open_card(panel)
    await panel.press("Удалить группу")
    confirm = panel.screen_button("Да, удалить")

    await panel.feed(button_press(confirm.callback_data, STRANGER))

    assert GROUP_KEY in panel.whitelist_on_disk()


async def test_sync_button_reconciles_with_telegram_and_reports(panel):
    panel.session.chat_members = {10: ("left", "alice")}
    await panel.open_groups()

    await panel.press(SYNC_LABEL)

    assert member_names(panel) == ["pending"]
    assert panel.last_toast() == "Проверяю участников…"
    assert "✅ Сверено с Telegram" in panel.current_screen().text
    assert "Alpha · 1" in panel.screen_labels()


async def test_sync_button_answers_the_press_only_once(panel):
    await panel.open_groups()
    answers_before = len(panel.calls_of(AnswerCallbackQuery))

    await panel.press(SYNC_LABEL)

    assert len(panel.calls_of(AnswerCallbackQuery)) == answers_before + 1


async def test_sync_button_stays_on_the_current_page(many_groups):
    await many_groups.open_groups()
    await many_groups.press("▶️")

    await many_groups.press(SYNC_LABEL)

    assert "Group 10 · 0" in many_groups.screen_labels()


async def test_clear_button_cleans_from_the_newest_message_and_reopens_the_panel(panel):
    await panel.feed(command("/start"))
    await panel.press("Очистить чат")

    sent = panel.calls_of(SendMessage)
    assert "Очищаю переписку" in sent[1].text
    first_batch = panel.calls_of(DeleteMessages)[0].message_ids
    assert first_batch[0] == FIRST_SENT_MESSAGE_ID + 1
    assert "Групп:" in sent[2].text
    assert "👥 Группы" in panel.screen_labels()


async def test_clear_button_while_a_cleanup_runs_is_refused(panel, held_cleanup):
    await panel.feed(command("/start"))
    press = button_press(panel.screen_button("Очистить чат").callback_data)

    await held_cleanup.run_second_while_first_is_running(
        panel, command("/clear", message_id=9), press
    )

    assert panel.last_toast() == "Очистка уже идёт."
    assert not any("Очищаю" in call.text for call in panel.calls_of(SendMessage))


async def test_double_tap_on_clear_sends_one_marker(panel):
    await panel.feed(command("/start"))
    press = button_press(panel.screen_button("Очистить чат").callback_data)
    panel.session.suspends = True

    await asyncio.gather(panel.feed(press), panel.feed(press))

    assert sum("Очищаю" in call.text for call in panel.calls_of(SendMessage)) == 1


async def test_failure_of_an_action_stops_the_spinner(panel):
    await open_card(panel)
    panel.paths.whitelist.write_text("{ broken", encoding="utf-8")

    await panel.press("Убрать")

    assert panel.last_toast() == "⚠️ Не получилось. Подробности в логе бота."
    assert "WhitelistCorruptedError" in panel.admin_notices()[-1]


async def test_admin_chat_receives_every_panel_result(panel):
    await start_adding(panel)
    await panel.feed(command("@newbie"))

    assert panel.current_screen().chat_id == ADMIN_ID


async def test_two_quick_messages_add_only_one_list(panel):
    await start_adding(panel)
    panel.session.suspends = True

    await asyncio.gather(panel.feed(command("@first_name")), panel.feed(command("@second_name")))

    assert len({"first_name", "second_name"} & set(member_names(panel))) == 1
    assert panel.no_failure_alert()


async def test_press_during_typed_input_is_not_a_failure(panel):
    await start_adding(panel)
    cancel = panel.screen_button("Отмена")

    await asyncio.gather(
        panel.feed(command("@newbie")), panel.feed(button_press(cancel.callback_data))
    )

    assert panel.no_failure_alert()


async def fail_to_write(self, whitelist):
    raise OSError("disk is gone")


async def test_failed_write_keeps_the_typed_message_and_the_wait(panel, monkeypatch):
    await start_adding(panel)

    with monkeypatch.context() as patch:
        patch.setattr(WhitelistStore, "_write", fail_to_write)
        await panel.feed(command("@newbie"))

    assert panel.calls_of(DeleteMessage) == []
    assert "Не получилось" in panel.calls_of(SendMessage)[-2].text
    assert "OSError" in panel.admin_notices()[-1]

    await panel.feed(command("@newbie"))

    assert "newbie" in member_names(panel)


async def test_unreadable_list_during_input_answers_every_time(panel):
    good_list = panel.paths.whitelist.read_text(encoding="utf-8")
    await start_adding(panel)
    panel.paths.whitelist.write_text("{ broken", encoding="utf-8")

    await panel.feed(command("@newbie"))
    await panel.feed(command("@newbie"))

    failures = [text for text in panel.admin_notices() if "Не получилось" in text]
    assert len(failures) == 2

    panel.paths.whitelist.write_text(good_list, encoding="utf-8")
    await panel.feed(command("@newbie"))

    assert "newbie" in member_names(panel)


async def test_prompt_that_could_not_be_shown_does_not_start_the_wait(panel):
    await open_card(panel)
    panel.session.script_errors(EditMessageText, network_failure())

    await panel.press("Добавить")
    await panel.feed(command("@newbie"))

    assert "newbie" not in member_names(panel)


async def test_invalid_text_after_the_group_is_gone_shows_the_list(panel):
    await start_adding(panel)
    panel.given_whitelist({"-1009": {"project": "Other", "members": []}})

    await panel.feed(command("@bad-name"))

    assert "Этой группы уже нет в списке." in panel.current_screen().text


async def test_photo_with_a_caption_is_not_taken_as_members(panel):
    await start_adding(panel)
    update = command("ignored")
    message = update["message"]
    del message["text"]
    message["caption"] = "@newbie"
    message["photo"] = [{"file_id": "f", "file_unique_id": "u", "width": 1, "height": 1}]

    await panel.feed(update)

    assert "newbie" not in member_names(panel)
    assert panel.no_failure_alert()


async def test_press_on_another_panel_ends_the_wait_and_text_gets_a_hint(panel):
    await panel.feed(command("/start"))
    status = panel.screen_button("Статус")
    await start_adding(panel)
    await panel.feed(button_press(status.callback_data, message_id=71))

    await panel.feed(command("@newbie"))

    assert "newbie" not in member_names(panel)
    assert "Сейчас бот ничего не ждёт" in panel.current_screen().text
    assert panel.calls_of(DeleteMessage) == []


async def test_plain_text_outside_a_wait_gets_a_hint_only_from_an_admin(panel):
    await panel.feed(command("hello", STRANGER))
    assert panel.calls_of(SendMessage) == []

    await panel.feed(command("hello", chat=supergroup()))
    assert panel.calls_of(SendMessage) == []

    await panel.feed(command("hello"))
    assert "Сейчас бот ничего не ждёт" in panel.current_screen().text


async def test_unknown_command_gets_no_hint(panel):
    await panel.feed(command("/unknown"))

    assert panel.calls_of(SendMessage) == []


class HeldSync:
    """Stands in for polling Telegram. The first run stays open until the test lets it finish."""

    def __init__(self):
        self.runs = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(self, bot, whitelist):
        self.runs += 1
        self.started.set()
        if self.runs == 1:
            await self.release.wait()
        return {}


@pytest.fixture
def held_sync(monkeypatch):
    sync = HeldSync()
    monkeypatch.setattr(access_list_changes, "_observe_all_members", sync)
    return sync


async def test_finishing_sync_does_not_replace_a_prompt(panel, held_sync):
    await panel.open_groups()
    running = asyncio.create_task(panel.press(SYNC_LABEL))
    async with asyncio.timeout(5):
        await held_sync.started.wait()
    await panel.press("Alpha")
    await panel.press("Добавить")

    held_sync.release.set()
    await running

    assert "Пришлите ники или ID" in panel.current_screen().text


async def test_second_tap_on_sync_is_refused_while_it_runs(panel, held_sync):
    await panel.open_groups()
    press = button_press(panel.screen_button(SYNC_LABEL).callback_data)
    running = asyncio.create_task(panel.feed(press))
    async with asyncio.timeout(5):
        await held_sync.started.wait()

    await panel.feed(press)
    held_sync.release.set()
    await running

    assert held_sync.runs == 1
    assert "Сверка уже идёт." in [call.text for call in panel.calls_of(AnswerCallbackQuery)]


async def test_failed_sync_can_be_run_again(panel, monkeypatch):
    await panel.open_groups()
    press = button_press(panel.screen_button(SYNC_LABEL).callback_data)
    with monkeypatch.context() as patch:
        patch.setattr(WhitelistStore, "_write", fail_to_write)
        panel.session.chat_members = {10: ("left", "alice")}
        await panel.feed(press)

    await panel.feed(press)

    assert "✅ Сверено с Telegram" in panel.current_screen().text


async def test_sync_stops_at_a_rate_limit_and_leaves_the_rest_unchecked(harness):
    members = [{"id": 1, "in": True}, {"id": 2, "in": True}]
    harness.given_whitelist({GROUP_KEY: {"project": "Alpha", "members": members}})
    harness.session.script_errors(GetChatMember, retry_after(1))
    await harness.open_groups()

    await harness.press(SYNC_LABEL)

    assert len(harness.calls_of(GetChatMember)) == 1
    assert harness.members_on_disk(GROUP_KEY) == members
    assert harness.no_failure_alert()
