import asyncio

import pytest
from aiogram.methods import (
    AnswerCallbackQuery,
    ApproveChatJoinRequest,
    BanChatMember,
    DeclineChatJoinRequest,
    EditMessageReplyMarkup,
    EditMessageText,
    GetChatMember,
    SendMessage,
    UnbanChatMember,
)

from tests.support import (
    ALICE_RECORD,
    GROUP_ID,
    GROUP_KEY,
    STRANGER,
    bad_request,
    bot_change,
    button_press,
    command,
    decode_error,
    join_request,
    make_user,
    member_change,
    network_failure,
    supergroup,
)

STRANGER_ID = STRANGER["id"]
UNDECIDED_ERROR = "Bad Request: CHAT_ADMIN_REQUIRED"


@pytest.fixture
def alpha(harness):
    harness.given_whitelist({GROUP_KEY: {"project": "Alpha", "members": [ALICE_RECORD]}})
    return harness


def last_edit_text(harness):
    return harness.calls_of(EditMessageText)[-1].text


def record_of_stranger(harness):
    return next(m for m in harness.members_on_disk(GROUP_KEY) if m.get("id") == STRANGER_ID)


async def receive_unlisted_notice(harness):
    await harness.feed(member_change("left", "member", STRANGER))


async def receive_declined_notice(harness):
    await harness.feed(join_request(STRANGER))


async def receive_undecided_notice(harness, decision=DeclineChatJoinRequest):
    harness.session.script_errors(decision, bad_request(UNDECIDED_ERROR))
    await harness.feed(join_request(STRANGER))


async def receive_bot_removed_notice(harness):
    await harness.feed(bot_change("administrator", "kicked"))


async def test_unlisted_member_notice_offers_list_and_kick(alpha):
    await receive_unlisted_notice(alpha)

    assert alpha.screen_labels() == ["✅ В список", "🚫 Выгнать"]
    assert "/add" not in alpha.current_screen().text


async def test_adding_an_unlisted_member_records_them_as_joined(alpha):
    alpha.session.chat_members = {STRANGER_ID: ("member", "bob")}
    await receive_unlisted_notice(alpha)

    await alpha.press("В список")

    record = record_of_stranger(alpha)
    assert record["in"] is True
    assert record["username"] == "bob"
    assert "ADD project=Alpha @bob" in alpha.audit_events()
    assert alpha.screen_labels() == []
    assert "✅ Добавлено: @bob" in last_edit_text(alpha)


async def test_adding_works_when_telegram_cannot_confirm_the_member(alpha):
    await receive_unlisted_notice(alpha)

    await alpha.press("В список")

    assert "in" not in record_of_stranger(alpha)
    assert alpha.no_failure_alert()


async def test_person_who_already_left_is_not_recorded_as_joined(alpha):
    alpha.session.chat_members = {STRANGER_ID: ("left", "bob")}
    await receive_unlisted_notice(alpha)

    await alpha.press("В список")

    assert "in" not in record_of_stranger(alpha)


async def test_kick_removes_the_person_but_lets_them_apply_again(alpha):
    await receive_unlisted_notice(alpha)

    await alpha.press("Выгнать")

    ban = alpha.calls_of(BanChatMember)[0]
    unban = alpha.calls_of(UnbanChatMember)[0]
    assert (ban.chat_id, ban.user_id) == (GROUP_ID, STRANGER_ID)
    assert (unban.chat_id, unban.user_id, unban.only_if_banned) == (GROUP_ID, STRANGER_ID, True)
    assert alpha.session.calls.index(ban) < alpha.session.calls.index(unban)
    assert f"KICK id={STRANGER_ID} project=Alpha" in alpha.audit_events()
    assert "🚫 Исключён из группы" in last_edit_text(alpha)
    assert alpha.screen_labels() == []


async def test_failed_kick_explains_and_keeps_the_buttons(alpha):
    await receive_unlisted_notice(alpha)
    alpha.session.script_errors(BanChatMember, bad_request("Bad Request: not enough rights"))

    await alpha.press("Выгнать")

    assert alpha.last_toast() == "Не вышло: боту нужно право банить участников."
    assert alpha.calls_of(EditMessageText) == []
    assert not any("KICK" in event for event in alpha.audit_events())
    assert alpha.no_failure_alert()


async def test_kick_is_skipped_when_another_admin_already_listed_the_person(alpha):
    await receive_unlisted_notice(alpha)
    kick = alpha.screen_button("Выгнать")
    await alpha.press("В список")

    await alpha.feed(button_press(kick.callback_data))

    assert alpha.calls_of(BanChatMember) == []
    assert "Человек уже в списке" in last_edit_text(alpha)


async def test_kick_works_after_the_group_left_the_list(alpha):
    await receive_unlisted_notice(alpha)
    kick = alpha.screen_button("Выгнать")
    alpha.given_whitelist({})

    await alpha.feed(button_press(kick.callback_data))

    assert len(alpha.calls_of(BanChatMember)) == 1
    assert f"KICK id={STRANGER_ID} project={GROUP_KEY}" in alpha.audit_events()


async def test_declined_request_notice_offers_to_add(alpha):
    await receive_declined_notice(alpha)

    assert alpha.screen_labels() == ["➕ Добавить в список"]


async def test_decline_in_an_unknown_group_has_nothing_to_add_to(alpha):
    await alpha.feed(join_request(STRANGER, supergroup(-1009)))

    assert alpha.screen_labels() == []


async def test_person_added_from_a_decline_is_approved_on_the_next_request(alpha):
    await receive_declined_notice(alpha)

    await alpha.press("Добавить в список")

    assert "Человеку нужно подать заявку снова" in last_edit_text(alpha)
    assert alpha.screen_labels() == []

    await alpha.feed(join_request(STRANGER))

    assert len(alpha.calls_of(ApproveChatJoinRequest)) == 1


async def test_adding_someone_already_listed_is_reported(alpha):
    await receive_declined_notice(alpha)
    add = alpha.screen_button("Добавить в список")
    await alpha.feed(button_press(add.callback_data))

    await alpha.feed(button_press(add.callback_data))

    assert f"⏭ Уже были: id {STRANGER_ID}" in last_edit_text(alpha)
    assert sum("ADD" in event for event in alpha.audit_events()) == 1


async def test_adding_to_a_deleted_group_is_explained(alpha):
    await receive_declined_notice(alpha)
    add = alpha.screen_button("Добавить в список")
    alpha.given_whitelist({})

    await alpha.feed(button_press(add.callback_data))

    assert "Этой группы уже нет в списке." in last_edit_text(alpha)
    assert "подать заявку снова" not in last_edit_text(alpha)
    assert alpha.whitelist_on_disk() == {}


async def test_undecided_request_notice_offers_both_decisions(alpha):
    await receive_undecided_notice(alpha)

    assert "Заявка не обработана" in alpha.current_screen().text
    assert alpha.screen_labels() == ["✅ Одобрить", "⛔ Отклонить"]


async def test_admin_approves_an_undecided_request(alpha):
    await receive_undecided_notice(alpha)

    await alpha.press("Одобрить")

    approve = alpha.calls_of(ApproveChatJoinRequest)[0]
    assert (approve.chat_id, approve.user_id) == (GROUP_ID, STRANGER_ID)
    assert f"APPROVED-MANUAL id={STRANGER_ID} project=Alpha" in alpha.audit_events()
    assert "Доступ подтверждён" in alpha.texts_sent_to(STRANGER_ID)[-1]
    assert "✅ Одобрено вручную" in last_edit_text(alpha)
    assert alpha.screen_labels() == []


async def test_admin_declines_an_undecided_request(alpha):
    await receive_undecided_notice(alpha)

    await alpha.press("Отклонить")

    assert len(alpha.calls_of(DeclineChatJoinRequest)) == 2
    assert alpha.calls_of(ApproveChatJoinRequest) == []
    assert f"DECLINED-MANUAL id={STRANGER_ID} project=Alpha" in alpha.audit_events()
    assert "Заявка отклонена" in alpha.texts_sent_to(STRANGER_ID)[-1]
    assert "⛔ Отклонено вручную" in last_edit_text(alpha)


async def test_request_someone_already_resolved_closes_the_notice(alpha):
    await receive_undecided_notice(alpha)
    alpha.session.script_errors(
        ApproveChatJoinRequest, bad_request("Bad Request: HIDE_REQUESTER_MISSING")
    )

    await alpha.press("Одобрить")

    assert "Заявка уже решена" in last_edit_text(alpha)
    assert not any("MANUAL" in event for event in alpha.audit_events())


async def test_decision_that_fails_again_keeps_the_buttons(alpha):
    await receive_undecided_notice(alpha)
    alpha.session.script_errors(ApproveChatJoinRequest, bad_request(UNDECIDED_ERROR))

    await alpha.press("Одобрить")

    assert alpha.last_toast() == "Telegram снова не принял решение. Попробуйте позже."
    assert alpha.calls_of(EditMessageText) == []
    assert not any("MANUAL" in event for event in alpha.audit_events())


async def test_decision_is_retried_after_a_network_failure(alpha):
    await receive_undecided_notice(alpha)
    alpha.session.script_errors(ApproveChatJoinRequest, network_failure())

    await alpha.press("Одобрить")

    assert len(alpha.calls_of(ApproveChatJoinRequest)) == 2
    assert "✅ Одобрено вручную" in last_edit_text(alpha)


async def test_decision_works_while_the_access_list_is_broken(alpha):
    await receive_undecided_notice(alpha)
    alpha.paths.whitelist.write_text("{ broken", encoding="utf-8")

    await alpha.press("Одобрить")

    assert len(alpha.calls_of(ApproveChatJoinRequest)) == 1
    assert f"APPROVED-MANUAL id={STRANGER_ID} project=проект" in alpha.audit_events()


async def test_bot_removed_notice_offers_to_forget_the_list(alpha):
    await receive_bot_removed_notice(alpha)

    assert alpha.screen_labels() == ["🗑 Удалить насовсем"]
    assert "/delgroup" not in alpha.current_screen().text


async def test_forgetting_a_list_asks_first(alpha):
    await receive_bot_removed_notice(alpha)

    await alpha.press("Удалить насовсем")

    assert GROUP_KEY in alpha.whitelist_on_disk()
    assert alpha.last_toast() == "Список нельзя будет вернуть."
    assert alpha.screen_labels() == ["Да, удалить", "Отмена"]
    assert alpha.screen_button("Да, удалить").style == "danger"
    assert alpha.calls_of(EditMessageText) == []


async def test_confirmed_forget_deletes_the_list(alpha):
    await receive_bot_removed_notice(alpha)
    await alpha.press("Удалить насовсем")

    await alpha.press("Да, удалить")

    assert alpha.whitelist_on_disk() == {}
    assert f"GROUP-DELETED {GROUP_KEY} «Alpha» (manual)" in alpha.audit_events()
    assert "🗑 Список удалён" in last_edit_text(alpha)
    assert alpha.screen_labels() == []


async def test_cancelled_forget_brings_the_first_button_back(alpha):
    await receive_bot_removed_notice(alpha)
    await alpha.press("Удалить насовсем")

    await alpha.press("Отмена")

    assert GROUP_KEY in alpha.whitelist_on_disk()
    assert alpha.screen_labels() == ["🗑 Удалить насовсем"]


async def test_list_is_kept_when_the_bot_has_returned_to_the_group(alpha):
    await receive_bot_removed_notice(alpha)
    await alpha.press("Удалить насовсем")
    confirm = alpha.screen_button("Да, удалить")
    await alpha.feed(bot_change("left", "administrator"))

    await alpha.feed(button_press(confirm.callback_data))

    assert GROUP_KEY in alpha.whitelist_on_disk()
    assert "Бот уже вернулся в группу" in last_edit_text(alpha)


async def test_forgetting_a_list_that_is_already_gone_is_explained(alpha):
    await receive_bot_removed_notice(alpha)
    await alpha.press("Удалить насовсем")
    confirm = alpha.screen_button("Да, удалить")
    alpha.given_whitelist({})

    await alpha.feed(button_press(confirm.callback_data))

    assert "Этой группы уже нет в списке." in last_edit_text(alpha)
    assert not any("GROUP-DELETED" in event for event in alpha.audit_events())


async def test_notice_buttons_do_nothing_for_a_non_admin(alpha):
    await receive_declined_notice(alpha)
    add = alpha.screen_button("Добавить в список")

    await alpha.feed(button_press(add.callback_data, make_user(555, "other")))

    assert len(alpha.members_on_disk(GROUP_KEY)) == 1
    assert alpha.last_toast() == "Эта кнопка больше не работает."


async def test_notice_buttons_do_nothing_inside_a_group(alpha):
    await receive_declined_notice(alpha)
    add = alpha.screen_button("Добавить в список")

    await alpha.feed(button_press(add.callback_data, chat=supergroup()))

    assert len(alpha.members_on_disk(GROUP_KEY)) == 1


async def test_result_keeps_the_formatting_of_the_notice(alpha):
    await receive_declined_notice(alpha)
    add = alpha.screen_button("Добавить в список")
    update = button_press(add.callback_data)
    message = update["callback_query"]["message"]
    message["text"] = "A&B id 99"
    message["entities"] = [{"type": "spoiler", "offset": 7, "length": 2}]

    await alpha.feed(update)

    assert last_edit_text(alpha).startswith("A&amp;B id <tg-spoiler>99</tg-spoiler>\n\n")


async def test_double_tap_acts_once(alpha):
    await receive_unlisted_notice(alpha)
    press = button_press(alpha.screen_button("Выгнать").callback_data)
    alpha.session.suspends = True

    await asyncio.gather(alpha.feed(press), alpha.feed(press))

    assert len(alpha.calls_of(BanChatMember)) == 1
    assert sum("KICK" in event for event in alpha.audit_events()) == 1
    assert "Уже выполняется." in [call.text for call in alpha.calls_of(AnswerCallbackQuery)]


async def test_notice_can_be_pressed_again_after_a_failure(alpha):
    await receive_unlisted_notice(alpha)
    press = button_press(alpha.screen_button("Выгнать").callback_data)
    alpha.session.script_errors(BanChatMember, bad_request("Bad Request: not enough rights"))
    await alpha.feed(press)

    await alpha.feed(press)

    assert "🚫 Исключён из группы" in last_edit_text(alpha)


async def test_repeated_press_with_nothing_to_change_is_not_a_failure(alpha):
    await receive_bot_removed_notice(alpha)
    alpha.session.script_errors(
        EditMessageReplyMarkup, bad_request("Bad Request: message is not modified")
    )

    await alpha.press("Удалить насовсем")

    assert alpha.no_failure_alert()


async def test_same_result_twice_is_not_a_failure(alpha):
    await receive_declined_notice(alpha)
    alpha.session.script_errors(
        EditMessageText, bad_request("Bad Request: message is not modified")
    )

    await alpha.press("Добавить в список")

    assert alpha.no_failure_alert()


async def test_failure_stops_the_spinner_and_alerts(alpha):
    await receive_declined_notice(alpha)
    add = alpha.screen_button("Добавить в список")
    alpha.paths.whitelist.write_text("{ broken", encoding="utf-8")

    await alpha.feed(button_press(add.callback_data))

    assert alpha.last_toast() == "⚠️ Не получилось. Подробности в логе бота."
    assert "WhitelistCorruptedError" in alpha.admin_notices()[-1]


async def test_buttons_fit_the_longest_chat_and_user_ids(alpha):
    longest_chat_id = -1009999999999999
    alpha.given_whitelist({str(longest_chat_id): {"project": "Zed", "members": []}})
    person = make_user(9_999_999_999, "bob")

    await alpha.feed(member_change("left", "member", person, supergroup(longest_chat_id)))

    assert alpha.screen_labels() == ["✅ В список", "🚫 Выгнать"]


async def test_notices_for_people_are_still_delivered_without_buttons_for_others(alpha):
    await receive_declined_notice(alpha)

    message_to_person = next(c for c in alpha.calls_of(SendMessage) if c.chat_id == STRANGER_ID)
    assert message_to_person.reply_markup is None


async def test_ban_is_retried_after_a_network_failure(alpha):
    await receive_unlisted_notice(alpha)
    alpha.session.script_errors(BanChatMember, network_failure())

    await alpha.press("Выгнать")

    assert len(alpha.calls_of(BanChatMember)) == 2
    assert "🚫 Исключён из группы" in last_edit_text(alpha)


async def test_adding_an_unlisted_member_to_a_deleted_group_is_explained(alpha):
    await receive_unlisted_notice(alpha)
    add = alpha.screen_button("В список")
    alpha.given_whitelist({})

    await alpha.feed(button_press(add.callback_data))

    assert "Этой группы уже нет в списке." in last_edit_text(alpha)


async def test_lifting_the_ban_is_retried_after_a_network_failure(alpha):
    await receive_unlisted_notice(alpha)
    alpha.session.script_errors(UnbanChatMember, network_failure())

    await alpha.press("Выгнать")

    assert len(alpha.calls_of(UnbanChatMember)) == 2
    assert "🚫 Исключён из группы" in last_edit_text(alpha)


async def test_ban_that_could_not_be_lifted_is_reported_honestly(alpha):
    await receive_unlisted_notice(alpha)
    alpha.session.script_errors(UnbanChatMember, bad_request("Bad Request: not enough rights"))

    await alpha.press("Выгнать")

    assert "бан снять не удалось" in last_edit_text(alpha)
    assert alpha.screen_labels() == []
    assert f"KICK-STILL-BANNED id={STRANGER_ID} project=Alpha" in alpha.audit_events()
    assert not any(event.startswith("KICK id") for event in alpha.audit_events())


async def test_kick_is_skipped_for_a_person_listed_by_username(alpha):
    person = make_user(77, "bobby_one")
    alpha.session.chat_members = {77: ("member", "bobby_one")}
    await alpha.feed(member_change("left", "member", person))
    kick = alpha.screen_button("Выгнать")
    await alpha.feed(command("/add Alpha @bobby_one"))

    await alpha.feed(button_press(kick.callback_data))

    assert alpha.calls_of(BanChatMember) == []
    assert {"username": "bobby_one"} in alpha.members_on_disk(GROUP_KEY)


async def test_declined_person_listed_by_username_is_not_listed_twice(alpha):
    person = make_user(77, "bobby_one")
    alpha.session.chat_members = {77: ("left", "bobby_one")}
    await alpha.feed(join_request(person))
    add = alpha.screen_button("Добавить в список")
    await alpha.feed(command("/add Alpha @bobby_one"))

    await alpha.feed(button_press(add.callback_data))

    assert len(alpha.members_on_disk(GROUP_KEY)) == 2
    assert "⏭ Уже были: @bobby_one" in last_edit_text(alpha)


async def test_unparsable_answer_about_a_person_does_not_fail_the_add(alpha):
    await receive_unlisted_notice(alpha)
    alpha.session.script_errors(GetChatMember, decode_error())

    await alpha.press("В список")

    assert f"✅ Добавлено: id {STRANGER_ID}" in last_edit_text(alpha)
    assert alpha.no_failure_alert()


async def test_person_is_told_only_after_the_decision(alpha):
    await receive_undecided_notice(alpha)
    calls_before = len(alpha.session.calls)

    await alpha.press("Одобрить")

    later = alpha.session.calls[calls_before:]
    approve = next(i for i, call in enumerate(later) if isinstance(call, ApproveChatJoinRequest))
    told = next(i for i, call in enumerate(later) if isinstance(call, SendMessage))
    assert approve < told


async def test_admin_learns_when_the_person_could_not_be_told(alpha):
    await receive_undecided_notice(alpha)
    alpha.session.script_errors(SendMessage, bad_request("Forbidden: bot can't initiate"))

    await alpha.press("Одобрить")

    assert "Сообщить человеку не удалось" in last_edit_text(alpha)


async def test_told_person_needs_no_remark(alpha):
    await receive_undecided_notice(alpha)

    await alpha.press("Отклонить")

    assert "Сообщить человеку не удалось" not in last_edit_text(alpha)


async def test_manual_approval_does_not_raise_an_intruder_alarm(alpha):
    await receive_undecided_notice(alpha)
    await alpha.press("Одобрить")

    await alpha.feed(member_change("left", "member", STRANGER))

    assert record_of_stranger(alpha)["in"] is True
    assert not any("Вход без доступа" in text for text in alpha.admin_notices())


async def test_manual_decline_does_not_add_to_the_list(alpha):
    await receive_undecided_notice(alpha)

    await alpha.press("Отклонить")

    assert len(alpha.members_on_disk(GROUP_KEY)) == 1


async def test_kick_while_the_list_is_broken_does_not_ban(alpha):
    await receive_unlisted_notice(alpha)
    kick = alpha.screen_button("Выгнать")
    alpha.paths.whitelist.write_text("{ broken", encoding="utf-8")

    await alpha.feed(button_press(kick.callback_data))

    assert alpha.calls_of(BanChatMember) == []
    assert alpha.last_toast() == "⚠️ Не получилось. Подробности в логе бота."


async def test_forget_while_the_list_is_broken_leaves_the_file(alpha):
    await receive_bot_removed_notice(alpha)
    await alpha.press("Удалить насовсем")
    confirm = alpha.screen_button("Да, удалить")
    alpha.paths.whitelist.write_text("{ broken", encoding="utf-8")

    await alpha.feed(button_press(confirm.callback_data))

    assert alpha.paths.whitelist.read_text(encoding="utf-8") == "{ broken"


async def test_two_different_notices_are_served_at_the_same_time(alpha):
    await receive_unlisted_notice(alpha)
    kick = alpha.screen_button("Выгнать").callback_data
    alpha.session.suspends = True

    await asyncio.gather(
        alpha.feed(button_press(kick, message_id=71)), alpha.feed(button_press(kick, message_id=72))
    )

    toasts = [call.text for call in alpha.calls_of(AnswerCallbackQuery)]
    assert "Уже выполняется." not in toasts


async def test_press_answered_too_late_still_acts(alpha):
    await receive_unlisted_notice(alpha)
    alpha.session.script_errors(AnswerCallbackQuery, bad_request("Bad Request: query is too old"))

    await alpha.press("Выгнать")

    assert len(alpha.calls_of(BanChatMember)) == 1
    assert "🚫 Исключён из группы" in last_edit_text(alpha)
