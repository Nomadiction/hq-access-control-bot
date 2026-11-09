import asyncio

from aiogram.methods import DeleteMessage, DeleteMessages, SendMessage

from hq_access_bot.handlers import public_commands
from tests.support import ADMIN_ID, STRANGER, command, make_user, retry_after, supergroup


async def test_admin_sees_admin_help(harness):
    await harness.feed(command("/start"))

    assert "<code>/add</code>" in harness.admin_notices()[0]


async def test_user_sees_public_help_with_support_contact(harness):
    await harness.feed(command("/help", STRANGER))

    reply = harness.texts_sent_to(99)[0]
    assert "<code>/add</code>" not in reply
    assert '<a href="https://t.me/helpdesk">@helpdesk</a>' in reply


async def test_id_reports_the_current_chat(harness):
    await harness.feed(command("/id", STRANGER, supergroup(-1005)))

    assert harness.texts_sent_to(-1005) == ["🆔 chat_id: <code>-1005</code>"]


async def test_me_shows_id_and_username(harness):
    await harness.feed(command("/me", STRANGER))

    assert "<code>99</code>" in harness.texts_sent_to(99)[0]
    assert "Username: @bob" in harness.texts_sent_to(99)[0]


async def test_me_warns_user_without_username(harness):
    await harness.feed(command("/me", make_user(50)))

    assert "не задан @username" in harness.texts_sent_to(50)[0]


async def test_clear_deletes_history_in_batches_then_greets(harness):
    await harness.feed(command("/clear", STRANGER, message_id=150))

    batches = [call.message_ids for call in harness.calls_of(DeleteMessages)]
    assert batches[0] == list(range(150, 50, -1))
    assert batches[1] == list(range(50, 0, -1))
    assert len(batches) == 2
    assert len(harness.texts_sent_to(99)) == 1


async def test_clear_falls_back_to_single_deletes(harness):
    harness.session.failing_methods.add(DeleteMessages)

    await harness.feed(command("/clear", STRANGER, message_id=2))

    assert [call.message_id for call in harness.calls_of(DeleteMessage)] == [2, 1]


async def test_clear_tolerates_undeletable_messages(harness):
    harness.session.failing_methods |= {DeleteMessages, DeleteMessage}

    await harness.feed(command("/clear", STRANGER, message_id=2))

    assert len(harness.calls_of(DeleteMessage)) == 2
    assert len(harness.texts_sent_to(99)) == 1


async def test_clear_is_ignored_in_groups(harness):
    await harness.feed(command("/clear", make_user(ADMIN_ID), supergroup()))

    assert harness.calls_of(DeleteMessages) == []
    assert harness.calls_of(SendMessage) == []


async def test_clear_covers_a_bounded_part_of_the_history(harness):
    await harness.feed(command("/clear", STRANGER, message_id=5000))

    batches = [call.message_ids for call in harness.calls_of(DeleteMessages)]
    assert len(batches) == 10
    assert batches[0][0] == 5000
    assert batches[-1][-1] == 4001


async def test_concurrent_clear_in_the_same_chat_is_ignored(harness):
    update = command("/clear", STRANGER, message_id=150)

    await asyncio.gather(harness.feed(update), harness.feed(update))

    assert len(harness.calls_of(DeleteMessages)) == 2


async def test_clear_can_run_again_once_finished(harness):
    update = command("/clear", STRANGER, message_id=50)

    await harness.feed(update)
    await harness.feed(update)

    assert len(harness.calls_of(DeleteMessages)) == 2


async def test_clear_stops_when_telegram_reports_overload(harness):
    harness.session.script_errors(DeleteMessages, retry_after(1))

    await harness.feed(command("/clear", STRANGER, message_id=250))

    assert len(harness.calls_of(DeleteMessages)) == 1
    assert harness.calls_of(DeleteMessage) == []
    assert len(harness.texts_sent_to(99)) == 1


async def test_clear_stops_when_single_deletes_hit_overload(harness):
    harness.session.failing_methods.add(DeleteMessages)
    harness.session.script_errors(DeleteMessage, retry_after(1))

    await harness.feed(command("/clear", STRANGER, message_id=5))

    assert len(harness.calls_of(DeleteMessage)) == 1


async def test_cleanups_across_chats_are_capped(harness, monkeypatch):
    monkeypatch.setattr(public_commands, "_MAX_CONCURRENT_CLEANUPS", 1)
    first = command("/clear", make_user(201), message_id=150)
    second = command("/clear", make_user(202), message_id=150)

    await asyncio.gather(harness.feed(first), harness.feed(second))

    assert {call.chat_id for call in harness.calls_of(DeleteMessages)} == {201}
