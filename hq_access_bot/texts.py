"""All bot messages, in Telegram HTML markup."""

from collections.abc import Mapping
from html import escape
from itertools import batched

from hq_access_bot.whitelist.identity import Person
from hq_access_bot.whitelist.models import Group, Member, MemberChange, Whitelist

UNKNOWN_PROJECT = "проект"

_BOT_TITLE = "🔑 <b>HQ Access Bot</b>"

ADMIN_WELCOME = (
    f"{_BOT_TITLE}\n"
    "<i>Пропускной контроль рабочих групп проектов.</i>\n\n"
    "<b>Как это работает</b>\n"
    "<blockquote>Пользователь подаёт заявку по пригласительной ссылке. Бот "
    "сверяет его со списком доступа проекта и <u>мгновенно</u> одобряет или "
    "отклоняет. Об отклонённых попытках приходит уведомление.</blockquote>\n\n"
    "<b>Команды</b>\n"
    "<code>/add</code> - добавить участников\n"
    "<code>/remove</code> - убрать участников\n"
    "<code>/reload</code> - списки доступа\n"
    "<code>/delgroup</code> - убрать группу из списка\n"
    "<code>/status</code> - статус и счётчики\n"
    "<code>/clear</code> - очистить переписку\n"
    "<code>/id</code> - узнать chat_id (в группе)\n"
    "<code>/me</code> - показать ваш ID\n\n"
    "<i>Новые проекты заводятся автоматически при добавлении бота в группу. "
    "Вышедших и кикнутых бот убирает из списка сам.</i>"
)

DECLINED_DIRECT_MESSAGE = (
    "⛔ <b>Заявка отклонена</b>\n"
    "Вашего аккаунта нет в списке доступа этого проекта.\n"
    "<i>Если это ошибка - напишите администратору, он добавит вас в список.</i>"
)

REQUEST_FAILED_DIRECT_MESSAGE = (
    "⚠️ <b>Заявку не удалось обработать</b>\n<i>Администратор уже предупреждён.</i>"
)

ADD_USAGE = (
    "Формат: <code>/add &lt;проект&gt; &lt;@username|id&gt; [ещё...]</code>\n\n"
    "<b>Например:</b>\n"
    "<blockquote>/add Alpha @user1\n"
    "/add Beta @user2 @user3 123456789</blockquote>"
)

REMOVE_USAGE = (
    "Формат: <code>/remove &lt;проект&gt; &lt;@username|id&gt; [ещё...]</code>\n\n"
    "<b>Например:</b>\n"
    "<blockquote>/remove Alpha @user1\n"
    "/remove Beta 123456789</blockquote>"
)

DELGROUP_USAGE = (
    "Формат: <code>/delgroup &lt;проект|chat_id&gt;</code>\n\n"
    "<b>Например:</b>\n"
    "<blockquote>/delgroup Test\n"
    "/delgroup -1001234567890</blockquote>"
)

EMPTY_WHITELIST = "Список доступа пуст."

BUTTON_GROUPS = "👥 Группы"
BUTTON_STATUS = "📊 Статус"
BUTTON_BACK = "← Назад"
BUTTON_PREVIOUS_PAGE = "◀️"
BUTTON_NEXT_PAGE = "▶️"
BUTTON_CLEAR_CHAT = "🧹 Очистить чат"
BUTTON_SYNC = "🔄 Сверить с Telegram"
BUTTON_ADD = "➕ Добавить"
BUTTON_ADD_MORE = "➕ Ещё"
BUTTON_REMOVE = "➖ Убрать"
BUTTON_DELETE_GROUP = "🗑 Удалить группу"
BUTTON_CONFIRM_DELETE = "Да, удалить"
BUTTON_CANCEL = "Отмена"
BUTTON_BACK_TO_GROUP = "← К группе"
BUTTON_ADD_TO_LIST = "✅ В список"
BUTTON_KICK = "🚫 Выгнать"
BUTTON_ADD_DECLINED = "➕ Добавить в список"
BUTTON_APPROVE = "✅ Одобрить"
BUTTON_DECLINE = "⛔ Отклонить"
BUTTON_FORGET_GROUP = "🗑 Удалить насовсем"

STALE_BUTTON_NOTICE = "Эта кнопка больше не работает."
GROUP_GONE_NOTICE = "Этой группы уже нет в списке."
BUTTON_FAILURE_NOTICE = "⚠️ Не получилось. Подробности в логе бота."
MEMBER_GONE_NOTICE = "Этого участника уже нет в списке."
GROUP_DELETED_NOTICE = "Группа удалена."
SYNC_STARTED_NOTICE = "Проверяю участников…"
SYNC_DONE_NOTE = "✅ Сверено с Telegram"
SYNC_BUSY_NOTICE = "Сверка уже идёт."
MEMBERS_INPUT_EMPTY = "⚠️ <b>Пришлите хотя бы один ник или ID.</b>"
NOT_WAITING_FOR_INPUT = "Сейчас бот ничего не ждёт. Панель управления: /start"
CLEANUP_BUSY_NOTICE = "Очистка уже идёт."
CLEARING_NOTICE = "🧹 Очищаю переписку…"
ACTION_BUSY_NOTICE = "Уже выполняется."
KICK_FAILED_NOTICE = "Не вышло: боту нужно право банить участников."
DECISION_FAILED_NOTICE = "Telegram снова не принял решение. Попробуйте позже."
FORGET_WARNING_NOTICE = "Список нельзя будет вернуть."

APPLY_AGAIN_HINT = "<i>Человеку нужно подать заявку снова.</i>"
ALREADY_LISTED_RESULT = "Человек уже в списке, исключать не стал."
KICKED_RESULT = "🚫 Исключён из группы."
APPROVED_RESULT = "✅ Одобрено вручную."
DECLINED_RESULT = "⛔ Отклонено вручную."
ALREADY_RESOLVED_RESULT = "Заявка уже решена."
GROUP_FORGOTTEN_RESULT = "🗑 Список удалён."
BOT_RETURNED_RESULT = "Бот уже вернулся в группу, список оставлен."
KICKED_BUT_BANNED_RESULT = (
    "⚠️ Человек исключён, но бан снять не удалось. "
    "Снимите его в настройках группы, иначе человек не сможет вернуться."
)
PERSON_NOT_TOLD_HINT = "<i>Сообщить человеку не удалось.</i>"

_MEMBERS_PER_CARD_PAGE = 25
_MAX_LABELS_IN_REPORT = 40
_MAX_INVALID_PIECES_SHOWN = 10
_MAX_INVALID_PIECE_LENGTH = 40

_SECONDS_PER_HOUR = 3600
_SECONDS_PER_MINUTE = 60

# Telegram's maximum message length, which it counts in UTF-16 code units.
_MESSAGE_LIMIT_UTF16_UNITS = 4096

_UTF16_UNIT_BYTES = 2


def format_user_welcome(support_username: str) -> str:
    return (
        f"{_BOT_TITLE}\n"
        "<i>Система доступа к рабочим группам проектов.</i>\n\n"
        "<blockquote>Чтобы войти в проект, откройте пригласительную ссылку и "
        "подайте заявку. Если вы в списке доступа - она одобрится <u>автоматически</u> "
        "за пару секунд. Если нет - доступ выдаёт администратор.</blockquote>\n\n"
        "<b>Команда</b>\n"
        "<code>/me</code> - показать ваш ID\n\n"
        f'По всем вопросам: <a href="https://t.me/{support_username}">@{support_username}</a>'
    )


def format_approved_direct_message(project: str) -> str:
    return (
        "✅ <b>Доступ подтверждён</b>\n"
        f"Добро пожаловать в проект <b>{_escape(project)}</b>.\n"
        "<i>Группа уже открыта в вашем списке чатов.</i>"
    )


def format_request_approved_notice(project: str, person: Person) -> str:
    return _format_request_notice("✅ <b>Заявка одобрена</b>", project, person)


def format_request_declined_notice(project: str, person: Person) -> str:
    return _format_request_notice("⛔ <b>Заявка отклонена</b>", project, person)


def format_request_failed_notice(project: str, person: Person) -> str:
    heading = "⚠️ <b>Заявка не обработана</b>"
    notice = _format_request_notice(heading, project, person)
    return f"{notice}\n<i>Telegram не принял решение. Решите заявку кнопками.</i>"


def format_unlisted_member_notice(project: str, person: Person) -> str:
    notice = _format_request_notice("🚨 <b>Вход без доступа</b>", project, person)
    return f"{notice}\n<i>Человека нет в списке доступа.</i>"


def format_member_left_notice(project: str, person: Person) -> str:
    who = f"@{_escape(person.username)}" if person.username else _escape(person.full_name)
    return (
        f"👋 <b>Участник вышел</b> · {_escape(project)}\n"
        f"👤 {who} · id {_wrap_in_spoiler(person.user_id)}\n"
        f"<i>Убран из списка доступа.</i>"
    )


def format_bot_removed_notice(title: str) -> str:
    return (
        f"👥 <b>Бот удалён из группы</b> · {_escape(title)}\n"
        f"<i>Список доступа сохранён и вернётся, когда бота добавят снова.</i>"
    )


def format_group_restored_notice(title: str) -> str:
    return f"👥 <b>Бот снова в группе</b> · {_escape(title)}\n<i>Список доступа восстановлен.</i>"


def format_group_renamed_notice(title: str) -> str:
    return f"✏️ <b>Группа переименована</b> · {_escape(title)}"


def format_missing_rights_notice(title: str) -> str:
    return (
        f"⚠️ <b>Не хватает прав</b> · {_escape(title)}\n"
        f"<i>Боту нужны права приглашать участников (без него не работают заявки) "
        f"и банить их (без него не работает кнопка «Выгнать»).</i>"
    )


def format_basic_group_notice(title: str) -> str:
    return (
        f"⚠️ <b>Добавлен в обычную группу</b> · {_escape(title)}\n"
        f"<i>Заявки на вступление работают только в супергруппах. Выдайте "
        f"боту права администратора - группа станет супергруппой и попадёт "
        f"в список доступа.</i>"
    )


def format_group_registered_notice(title: str) -> str:
    return (
        f"👥 <b>Группа добавлена в систему</b>\n"
        f"<b>{_escape(title)}</b>\n"
        f"<i>Пока пустая.</i> Добавить людей: <code>/add {_escape(title)} @username</code>"
    )


def format_bot_promoted_notice(title: str) -> str:
    return f"✅ <b>Бот назначен администратором</b> · {_escape(title)}"


def format_bot_demoted_notice(title: str) -> str:
    return (
        f"⚠️ <b>У бота забрали админку</b> · {_escape(title)}\n"
        f"<i>Заявки не обрабатываются, участники не отслеживаются. "
        f"Верните боту права администратора.</i>"
    )


def format_chat_id_reply(chat_id: int) -> str:
    return f"🆔 chat_id: <code>{chat_id}</code>"


def format_own_id_reply(person: Person) -> str:
    if person.username:
        return f"🆔 Ваш ID: <code>{person.user_id}</code>\n👤 Username: @{_escape(person.username)}"
    return (
        f"🆔 Ваш ID: <code>{person.user_id}</code>\n"
        f"⚠️ <b>У вас не задан @username.</b> Передайте этот ID администратору - "
        f"он добавит вас по нему. Нажмите на номер, чтобы скопировать."
    )


def format_status_report(uptime_seconds: int, whitelist: Whitelist) -> str:
    hours, remainder_seconds = divmod(uptime_seconds, _SECONDS_PER_HOUR)
    minutes = remainder_seconds // _SECONDS_PER_MINUTE
    return (
        "📊 <b>Статус бота</b>\n"
        "Состояние: <b>работает</b> ✅\n"
        f"Аптайм: <b>{hours} ч {minutes} мин</b>\n"
        f"{_format_counts(whitelist)}"
    )


def format_panel_home(whitelist: Whitelist) -> str:
    return f"{_BOT_TITLE}\n{_format_counts(whitelist)}\n\n<i>Все команды: /help</i>"


def format_groups_title(page: int, page_count: int, notice: str | None = None) -> str:
    title = f"👥 <b>Группы</b>\n<i>Выберите проект</i>{_format_page_footer(page, page_count)}"
    return f"{notice}\n\n{title}" if notice else title


def format_add_prompt(group: Group, error: str | None = None) -> str:
    prompt = (
        f"➕ {_format_group_header(group)}\n"
        "Пришлите ники или ID одним сообщением.\n"
        "<i>Например: @user1 @user2 123456789</i>"
    )
    return f"{error}\n\n{prompt}" if error else prompt


def format_remove_title(group: Group, page: int, page_count: int) -> str:
    hint = "Нажмите на участника, чтобы убрать его." if group.members else "Убирать некого."
    return f"➖ {_format_group_header(group)}\n<i>{hint}</i>{_format_page_footer(page, page_count)}"


def format_member_button(member: Member) -> str:
    who = member.full_name if member.full_name and not member.username else member.ref.label
    return f"❌ {who}"


def format_member_removed_notice(label: str) -> str:
    return f"Убран: {label}"


def format_delete_confirmation(group: Group) -> str:
    return (
        f"🗑 {_format_group_header(group)}\n"
        f"Удалить группу из списка? Участников: <b>{len(group.members)}</b>.\n"
        "<i>Вернуть список будет нельзя, заявки в эту группу начнут отклоняться.</i>"
    )


def format_group_button(group: Group) -> str:
    label = f"{group.project} · {len(group.members)}"
    return label if group.is_active else f"💤 {label}"


def format_group_card_pages(chat_key: str, group: Group) -> list[str]:
    """Render a group as pages: a long list has to stay readable and within Telegram's limit."""
    header = (
        f"{_format_group_header(group)}\n"
        f"Участников: <b>{len(group.members)}</b> · chat_id <code>{chat_key}</code>\n\n"
    )
    member_count = len(group.members)
    # Every page holds at least one member, so the longest footer is the one on page N of N.
    longest_footer = _format_page_footer(member_count - 1, member_count)
    unit_limit = (
        _MESSAGE_LIMIT_UTF16_UNITS - _count_utf16_units(header) - _count_utf16_units(longest_footer)
    )
    pages = [
        page
        for chunk in batched(_format_member_lines(group), _MEMBERS_PER_CARD_PAGE)
        for page in _split_into_messages(list(chunk), unit_limit)
    ]
    return [
        f"{header}{page}{_format_page_footer(index, len(pages))}"
        for index, page in enumerate(pages)
    ]


def format_group_not_found(target: str) -> str:
    return f"Не нашёл группу: <b>{_escape(target)}</b>"


def format_group_ambiguous(target: str, groups: Mapping[str, Group]) -> str:
    key_lines = "\n".join(
        f"<code>{chat_key}</code> · {_format_group_header(group)}"
        for chat_key, group in groups.items()
    )
    return f"Несколько групп называются <b>{_escape(target)}</b>. Укажите chat_id:\n{key_lines}"


def format_invalid_usernames(usernames: list[str]) -> str:
    shown = [piece[:_MAX_INVALID_PIECE_LENGTH] for piece in usernames[:_MAX_INVALID_PIECES_SHOWN]]
    return (
        f"⚠️ <b>Некорректные ники:</b> {_escape(', '.join(shown))}\n"
        f"<i>Ник Telegram: латиница, цифры и подчёркивание, первый символ буква.</i>"
    )


def format_internal_error_notice(error_name: str) -> str:
    return (
        f"⚠️ <b>Сбой в работе бота</b>\n"
        f"<code>{_escape(error_name)}</code>\n"
        f"<i>Подробности в логе.</i>"
    )


def format_add_report(project: str, change: MemberChange) -> str:
    lines = [f"<b>{_escape(project)}</b>"]
    if change.applied:
        lines.append("✅ Добавлено: " + _format_labels(change.applied))
    if change.skipped:
        lines.append("⏭ Уже были: " + _format_labels(change.skipped))
    return "\n".join(lines)


def format_removal_report(project: str, change: MemberChange) -> str:
    if change.applied:
        return f"<b>{_escape(project)}</b>\n🗑 Удалено: " + _format_labels(change.applied)
    return f"<b>{_escape(project)}</b>\nНикого не нашёл для удаления."


def format_group_deleted_reply(project: str) -> str:
    return f"🗑 Группа <b>{_escape(project)}</b> убрана из списка доступа."


def format_access_list_messages(whitelist: Whitelist) -> list[str]:
    """Render the access lists as one or more messages that fit Telegram's size limit."""
    lines = ["📋 <b>Списки доступа</b>"]
    for group in whitelist.groups.values():
        lines += ["", _format_group_header(group), *_format_member_lines(group)]
    return _split_into_messages(lines)


def _split_into_messages(
    lines: list[str], unit_limit: int = _MESSAGE_LIMIT_UTF16_UNITS
) -> list[str]:
    """Group whole lines into messages, so a split never falls inside an HTML tag."""
    messages: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if _count_utf16_units(candidate) > unit_limit:
            messages.append(current.rstrip("\n"))
            current = line
        else:
            current = candidate
    messages.append(current)
    return messages


def _count_utf16_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // _UTF16_UNIT_BYTES


def _format_labels(labels: list[str]) -> str:
    """List members in a report, which has to fit one message however many there are."""
    shown = ", ".join(labels[:_MAX_LABELS_IN_REPORT])
    hidden_count = len(labels) - _MAX_LABELS_IN_REPORT
    return _escape(f"{shown} и ещё {hidden_count}" if hidden_count > 0 else shown)


def _format_counts(whitelist: Whitelist) -> str:
    return (
        f"Групп: <b>{len(whitelist.groups)}</b> · "
        f"Участников: <b>{whitelist.count_unique_members()}</b>"
    )


def _format_page_footer(page: int, page_count: int) -> str:
    return f"\n\n<i>Стр. {page + 1} из {page_count}</i>" if page_count > 1 else ""


def _format_member_lines(group: Group) -> list[str]:
    return [_format_member_line(member) for member in group.members] or ["<i>пусто</i>"]


def _format_group_header(group: Group) -> str:
    header = f"<b>{_escape(group.project)}</b>"
    return header if group.is_active else f"{header} <i>(бот не в группе)</i>"


def _format_request_notice(heading: str, project: str, person: Person) -> str:
    handle = f"@{_escape(person.username)}" if person.username else "<i>без username</i>"
    return (
        f"{heading} · {_escape(project)}\n"
        f"👤 {_escape(person.full_name)} · {handle}\n"
        f"id {_wrap_in_spoiler(person.user_id)}"
    )


def _format_member_line(member: Member) -> str:
    if member.username:
        who = f"@{_escape(member.username)}"
    elif member.full_name:
        who = f"{_escape(member.full_name)} <i>(без @username)</i>"
    else:
        who = "<i>без имени</i>"
    line = f"• {who}"
    if member.user_id is not None:
        line += f" {_wrap_in_spoiler(member.user_id)}"
    if not member.has_joined:
        line += " <i>· ожидает входа</i>"
    return line


def _escape(value: object) -> str:
    return escape(str(value), quote=False)


def _wrap_in_spoiler(value: object) -> str:
    # With a nested <code>, Telegram drops the spoiler and shows the text in the clear.
    return f"<tg-spoiler>{_escape(value)}</tg-spoiler>"
