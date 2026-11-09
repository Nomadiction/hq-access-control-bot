import time

import pytest
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage

from tests.support import (
    ADMIN_ID,
    ALICE_RECORD,
    GROUP_KEY,
    PANEL_MESSAGE_ID,
    STRANGER,
    TELEGRAM_MESSAGE_LIMIT,
    bad_request,
    button_press,
    command,
    count_utf16_units,
    make_user,
    supergroup,
)

INACTIVE_KEY = "-1002"
LONGEST_CHAT_KEY = "-1009999999999999"
CALLBACK_DATA_LIMIT_BYTES = 64
MAX_CARD_PAGES_IN_A_TEST = 20

# With this name length a full page of members lands within the room kept for the page footer.
NAME_FILLING_THE_FOOTER_ROOM = "я" * 124


@pytest.fixture
def panel(harness):
    harness.given_whitelist(
        {
            GROUP_KEY: {"project": "Alpha", "members": [ALICE_RECORD, {"username": "pending"}]},
            INACTIVE_KEY: {"project": "Old", "members": [{"id": 20}], "inactive": True},
        }
    )
    return harness


async def test_start_opens_the_panel_for_an_admin(panel):
    await panel.feed(command("/start"))

    assert "Групп: <b>2</b> · Участников: <b>3</b>" in panel.current_screen().text
    assert panel.screen_labels() == ["👥 Группы", "📊 Статус"]


async def test_start_shows_no_panel_to_other_users(panel):
    await panel.feed(command("/start", STRANGER))

    assert panel.screen_labels() == []
    assert "@helpdesk" in panel.current_screen().text


async def test_start_shows_no_panel_inside_a_group(panel):
    await panel.feed(command("/start", chat=supergroup()))

    assert panel.screen_labels() == []


async def test_clear_returns_an_admin_to_the_panel(panel):
    await panel.feed(command("/clear", message_id=1))

    assert panel.screen_labels() == ["👥 Группы", "📊 Статус"]


async def test_button_changes_the_pressed_message_instead_of_sending_a_new_one(panel):
    await panel.open_groups()

    assert len(panel.calls_of(SendMessage)) == 1
    edit = panel.calls_of(EditMessageText)[0]
    assert (edit.chat_id, edit.message_id) == (ADMIN_ID, PANEL_MESSAGE_ID)
    assert panel.calls_of(AnswerCallbackQuery)


async def test_groups_screen_lists_projects_with_member_counts(panel):
    await panel.open_groups()

    assert panel.screen_labels() == ["Alpha · 2", "💤 Old · 1", "← Назад"]


async def test_groups_screen_says_when_the_list_is_empty(harness):
    await harness.open_groups()

    assert "Список доступа пуст" in harness.current_screen().text
    assert harness.screen_labels() == ["← Назад"]


async def test_group_card_shows_members_and_chat_id(panel):
    await panel.open_groups()
    await panel.press("Alpha")

    card = panel.current_screen().text
    assert "<b>Alpha</b>" in card
    assert f"<code>{GROUP_KEY}</code>" in card
    assert "Участников: <b>2</b>" in card
    assert "@alice" in card
    assert "@pending <i>· ожидает входа</i>" in card
    assert "Стр." not in card


async def test_group_card_marks_a_group_the_bot_left(panel):
    await panel.open_groups()
    await panel.press("Old")

    assert "<i>(бот не в группе)</i>" in panel.current_screen().text


async def test_group_card_says_when_a_group_has_no_members(harness):
    harness.given_whitelist({GROUP_KEY: {"project": "Alpha", "members": []}})
    await harness.open_groups()
    await harness.press("Alpha")

    assert "<i>пусто</i>" in harness.current_screen().text


async def test_back_buttons_walk_up_to_the_main_screen(panel):
    await panel.open_groups()
    await panel.press("Alpha")

    await panel.press("Назад")
    assert "Alpha · 2" in panel.screen_labels()

    await panel.press("Назад")
    assert panel.screen_labels() == ["👥 Группы", "📊 Статус"]


async def test_status_button_reports_uptime_and_counts(panel):
    await panel.feed(command("/start"))
    await panel.press("Статус")

    report = panel.current_screen().text
    assert "Аптайм:" in report
    assert "Групп: <b>2</b> · Участников: <b>3</b>" in report
    assert panel.screen_labels() == ["← Назад"]


@pytest.fixture
def many_groups(harness):
    harness.given_whitelist(
        {str(-1000 - i): {"project": f"Group {i:02}", "members": []} for i in reversed(range(12))}
    )
    return harness


async def test_groups_are_sorted_and_split_into_pages(many_groups):
    await many_groups.open_groups()

    labels = many_groups.screen_labels()
    assert labels[:10] == [f"Group {i:02} · 0" for i in range(10)]
    assert labels[10:] == ["▶️", "← Назад"]
    assert "Стр. 1 из 2" in many_groups.current_screen().text


async def test_last_groups_page_can_only_go_back(many_groups):
    await many_groups.open_groups()
    await many_groups.press("▶️")

    assert many_groups.screen_labels() == ["Group 10 · 0", "Group 11 · 0", "◀️", "← Назад"]
    assert "Стр. 2 из 2" in many_groups.current_screen().text


async def test_group_card_returns_to_the_page_it_was_opened_from(many_groups):
    await many_groups.open_groups()
    await many_groups.press("▶️")
    await many_groups.press("Group 11")
    await many_groups.press("Назад")

    assert "Group 10 · 0" in many_groups.screen_labels()


async def collect_card_pages(harness):
    await harness.open_groups()
    await harness.press("Big")
    pages = [harness.current_screen().text]
    for _ in range(MAX_CARD_PAGES_IN_A_TEST):
        if "▶️" not in harness.screen_labels():
            return pages
        await harness.press("▶️")
        pages.append(harness.current_screen().text)
    pytest.fail("the next page button never disappears")


async def test_group_card_shows_a_limited_number_of_members_per_page(harness):
    members = [{"username": f"user_{i:03}"} for i in range(60)]
    harness.given_whitelist({GROUP_KEY: {"project": "Big", "members": members}})

    pages = await collect_card_pages(harness)

    assert len(pages) == 3
    assert "@user_024" in pages[0]
    assert "@user_025" not in pages[0]
    assert "Участников: <b>60</b>" in pages[2]
    assert "Стр. 3 из 3" in pages[2]


async def test_every_card_page_fits_the_telegram_limit_and_no_member_is_lost(harness):
    members = [
        {"id": 1000 + i, "in": True, "name": f"{i:03}{NAME_FILLING_THE_FOOTER_ROOM}"}
        for i in range(90)
    ]
    harness.given_whitelist({GROUP_KEY: {"project": "Big", "members": members}})

    pages = await collect_card_pages(harness)

    assert all(count_utf16_units(page) <= TELEGRAM_MESSAGE_LIMIT for page in pages)
    assert all(any(str(1000 + i) in page for page in pages) for i in range(90))


async def test_card_page_that_no_longer_exists_shows_the_last_one(harness):
    members = [{"username": f"user_{i:03}"} for i in range(30)]
    harness.given_whitelist({GROUP_KEY: {"project": "Big", "members": members}})
    await harness.open_groups()
    await harness.press("Big")
    next_page = harness.screen_button("▶️")
    harness.given_whitelist({GROUP_KEY: {"project": "Big", "members": members[:5]}})

    await harness.feed(button_press(next_page.callback_data))

    assert "@user_004" in harness.current_screen().text
    assert harness.screen_labels() == ["← Назад"]


async def test_groups_page_that_no_longer_exists_shows_the_last_one(many_groups):
    await many_groups.open_groups()
    next_page = many_groups.screen_button("▶️")
    many_groups.given_whitelist({GROUP_KEY: {"project": "Only", "members": []}})

    await many_groups.feed(button_press(next_page.callback_data))

    assert many_groups.screen_labels() == ["Only · 0", "← Назад"]


async def test_group_buttons_go_two_in_a_row(many_groups):
    await many_groups.open_groups()

    rows = many_groups.current_screen().reply_markup.inline_keyboard
    assert [len(row) for row in rows] == [2, 2, 2, 2, 2, 1, 1]


async def test_button_data_stays_within_the_telegram_limit(harness):
    members = [{"username": f"user_{i:03}"} for i in range(30)]
    groups = {str(-1000 - i): {"project": f"Group {i:02}", "members": []} for i in range(30)}
    harness.given_whitelist({**groups, LONGEST_CHAT_KEY: {"project": "Zed", "members": members}})
    await harness.open_groups()
    for _ in range(3):
        await harness.press("▶️")
    await harness.press("Zed")
    await harness.press("▶️")

    sizes = [len(button.callback_data.encode()) for button in harness.screen_buttons()]
    assert max(sizes) <= CALLBACK_DATA_LIMIT_BYTES


async def test_button_of_a_deleted_group_explains_and_shows_the_list(panel):
    await panel.open_groups()
    alpha = panel.screen_button("Alpha")
    panel.given_whitelist({INACTIVE_KEY: {"project": "Old", "members": []}})

    await panel.feed(button_press(alpha.callback_data))

    assert panel.last_toast() == "Этой группы уже нет в списке."
    assert panel.screen_labels() == ["Old · 0", "← Назад"]


async def test_panel_buttons_do_nothing_for_a_non_admin(panel):
    await panel.feed(command("/start"))
    groups_button = panel.screen_buttons()[0]

    await panel.feed(button_press(groups_button.callback_data, STRANGER))

    assert panel.calls_of(EditMessageText) == []
    assert panel.last_toast() == "Эта кнопка больше не работает."


async def test_panel_buttons_do_nothing_inside_a_group(panel):
    await panel.feed(command("/start"))
    groups_button = panel.screen_buttons()[0]

    await panel.feed(button_press(groups_button.callback_data, chat=supergroup()))

    assert panel.calls_of(EditMessageText) == []
    assert panel.last_toast() == "Эта кнопка больше не работает."


async def test_unknown_button_gets_an_answer(panel):
    await panel.feed(button_press("retired:button"))

    assert panel.calls_of(EditMessageText) == []
    assert panel.last_toast() == "Эта кнопка больше не работает."


async def test_button_on_a_message_telegram_no_longer_shows_gets_an_answer(panel):
    await panel.feed(command("/start"))
    update = button_press(panel.screen_buttons()[0].callback_data)
    update["callback_query"]["message"] = {
        "message_id": 5,
        "date": 0,
        "chat": {"id": ADMIN_ID, "type": "private"},
    }

    await panel.feed(update)

    assert panel.calls_of(EditMessageText) == []
    assert panel.last_toast() == "Эта кнопка больше не работает."


async def test_pressing_the_same_button_twice_is_not_a_failure(panel):
    panel.session.script_errors(
        EditMessageText, bad_request("Bad Request: message is not modified: same content")
    )
    await panel.feed(command("/start"))

    await panel.press("Группы")

    assert panel.admin_notices() == [panel.calls_of(SendMessage)[0].text]


async def test_a_real_edit_failure_reaches_the_admins(panel):
    panel.session.script_errors(EditMessageText, bad_request("Bad Request: message not found"))
    await panel.feed(command("/start"))

    await panel.press("Группы")

    assert "Сбой в работе бота" in panel.admin_notices()[-1]
    assert panel.calls_of(AnswerCallbackQuery)


async def test_a_press_answered_too_late_still_changes_the_screen(panel):
    panel.session.script_errors(AnswerCallbackQuery, bad_request("Bad Request: query is too old"))
    await panel.feed(command("/start"))

    await panel.press("Группы")

    assert len(panel.calls_of(EditMessageText)) == 1
    assert len(panel.admin_notices()) == 1


async def test_status_button_counts_uptime_from_the_start_of_the_bot(panel):
    panel.dispatcher["started_at_seconds"] = time.monotonic() - 7500
    await panel.feed(command("/start"))

    await panel.press("Статус")

    assert "2 ч 5 мин" in panel.current_screen().text


async def test_previous_page_button_returns_to_the_earlier_groups(many_groups):
    await many_groups.open_groups()
    await many_groups.press("▶️")

    await many_groups.press("◀️")

    assert "Group 00 · 0" in many_groups.screen_labels()


async def test_previous_page_button_returns_to_the_earlier_members(harness):
    members = [{"username": f"user_{i:03}"} for i in range(30)]
    harness.given_whitelist({GROUP_KEY: {"project": "Big", "members": members}})
    await collect_card_pages(harness)

    await harness.press("◀️")

    assert "@user_000" in harness.current_screen().text


async def test_paging_through_a_card_keeps_the_page_of_the_group_list(harness):
    members = [{"username": f"user_{i:03}"} for i in range(30)]
    groups = {str(-1000 - i): {"project": f"Group {i:02}", "members": []} for i in range(12)}
    harness.given_whitelist({**groups, "-2000": {"project": "Zed", "members": members}})
    await harness.open_groups()
    await harness.press("▶️")
    await harness.press("Zed")
    await harness.press("▶️")

    await harness.press("Назад")

    assert "Group 10 · 0" in harness.screen_labels()


async def test_button_of_a_deleted_group_stays_on_its_page_of_the_list(many_groups):
    await many_groups.open_groups()
    await many_groups.press("▶️")
    deleted = many_groups.screen_button("Group 11")
    remaining = {str(-1000 - i): {"project": f"Group {i:02}", "members": []} for i in range(11)}
    many_groups.given_whitelist(remaining)

    await many_groups.feed(button_press(deleted.callback_data))

    assert many_groups.screen_labels() == ["Group 10 · 0", "◀️", "← Назад"]
    assert many_groups.last_toast() == "Этой группы уже нет в списке."


async def test_groups_are_sorted_regardless_of_letter_case(harness):
    names = ["beta", "Zed", "Alpha"]
    harness.given_whitelist(
        {str(-1000 - i): {"project": name, "members": []} for i, name in enumerate(names)}
    )

    await harness.open_groups()

    assert harness.screen_labels()[:3] == ["Alpha · 0", "beta · 0", "Zed · 0"]


async def test_group_name_is_plain_on_a_button_and_escaped_in_the_card(harness):
    harness.given_whitelist({GROUP_KEY: {"project": "A&B", "members": []}})

    await harness.open_groups()
    assert harness.screen_labels()[0] == "A&B · 0"

    await harness.press("A&B")
    assert "<b>A&amp;B</b>" in harness.current_screen().text


async def test_group_card_is_not_shown_to_a_non_admin(panel):
    await panel.open_groups()
    alpha = panel.screen_button("Alpha")
    edits_before = len(panel.calls_of(EditMessageText))

    await panel.feed(button_press(alpha.callback_data, make_user(555, "former")))

    assert len(panel.calls_of(EditMessageText)) == edits_before
