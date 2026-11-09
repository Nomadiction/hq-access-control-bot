"""All bot messages, in Telegram HTML markup."""

from collections.abc import Mapping
from html import escape

from hq_access_bot.whitelist.identity import Person
from hq_access_bot.whitelist.models import Group, Member, MemberChange, Whitelist

UNKNOWN_PROJECT = "проект"

ADMIN_WELCOME = (
    "🔑 <b>HQ Access Bot</b>\n"
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

_SECONDS_PER_HOUR = 3600
_SECONDS_PER_MINUTE = 60

# Telegram's maximum message length, which it counts in UTF-16 code units.
_MESSAGE_LIMIT_UTF16_UNITS = 4096

_UTF16_UNIT_BYTES = 2


def format_user_welcome(support_username: str) -> str:
    return (
        "🔑 <b>HQ Access Bot</b>\n"
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
    return f"{notice}\n<i>Telegram не принял решение. Обработайте заявку вручную.</i>"


def format_unlisted_member_notice(project: str, person: Person, chat_key: str) -> str:
    notice = _format_request_notice("🚨 <b>Вход без доступа</b>", project, person)
    return (
        f"{notice}\n<i>Человека нет в списке доступа.</i> "
        f"Добавить: <code>/add {chat_key} {person.user_id}</code>"
    )


def format_member_left_notice(project: str, person: Person) -> str:
    who = f"@{_escape(person.username)}" if person.username else _escape(person.full_name)
    return (
        f"👋 <b>Участник вышел</b> · {_escape(project)}\n"
        f"👤 {who} · id {_wrap_in_spoiler(person.user_id)}\n"
        f"<i>Убран из списка доступа.</i>"
    )


def format_bot_removed_notice(title: str, chat_key: str) -> str:
    return (
        f"👥 <b>Бот удалён из группы</b> · {_escape(title)}\n"
        f"<i>Список доступа сохранён и вернётся, когда бота добавят снова.</i>\n"
        f"Удалить насовсем: <code>/delgroup {chat_key}</code>"
    )


def format_group_restored_notice(title: str) -> str:
    return f"👥 <b>Бот снова в группе</b> · {_escape(title)}\n<i>Список доступа восстановлен.</i>"


def format_group_renamed_notice(title: str) -> str:
    return f"✏️ <b>Группа переименована</b> · {_escape(title)}"


def format_missing_rights_notice(title: str) -> str:
    return (
        f"⚠️ <b>Не хватает прав</b> · {_escape(title)}\n"
        f"<i>Сделайте бота администратором с правом приглашать участников, "
        f"иначе заявки не будут обрабатываться.</i>"
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


def format_status_report(uptime_seconds: int, group_count: int, member_count: int) -> str:
    hours, remainder_seconds = divmod(uptime_seconds, _SECONDS_PER_HOUR)
    minutes = remainder_seconds // _SECONDS_PER_MINUTE
    return (
        "📊 <b>Статус бота</b>\n"
        "Состояние: <b>работает</b> ✅\n"
        f"Аптайм: <b>{hours} ч {minutes} мин</b>\n"
        f"Групп: <b>{group_count}</b> · Участников: <b>{member_count}</b>"
    )


def format_group_not_found(target: str) -> str:
    return f"Не нашёл группу: <b>{_escape(target)}</b>"


def format_group_ambiguous(target: str, groups: Mapping[str, Group]) -> str:
    key_lines = "\n".join(
        f"<code>{chat_key}</code> · {_format_group_header(group)}"
        for chat_key, group in groups.items()
    )
    return f"Несколько групп называются <b>{_escape(target)}</b>. Укажите chat_id:\n{key_lines}"


def format_invalid_usernames(usernames: list[str]) -> str:
    return (
        f"⚠️ <b>Некорректные ники:</b> {_escape(', '.join(usernames))}\n"
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
        lines.append("✅ Добавлено: " + _escape(", ".join(change.applied)))
    if change.skipped:
        lines.append("⏭ Уже были: " + _escape(", ".join(change.skipped)))
    return "\n".join(lines)


def format_removal_report(project: str, change: MemberChange) -> str:
    if change.applied:
        return f"<b>{_escape(project)}</b>\n🗑 Удалено: " + _escape(", ".join(change.applied))
    return f"<b>{_escape(project)}</b>\nНикого не нашёл для удаления."


def format_group_deleted_reply(project: str) -> str:
    return f"🗑 Группа <b>{_escape(project)}</b> убрана из списка доступа."


def format_access_list_messages(whitelist: Whitelist) -> list[str]:
    """Render the access lists as one or more messages that fit Telegram's size limit."""
    lines = ["📋 <b>Списки доступа</b>"]
    for group in whitelist.groups.values():
        member_lines = [_format_member_line(m) for m in group.members] or ["<i>пусто</i>"]
        lines += ["", _format_group_header(group), *member_lines]
    return _split_into_messages(lines)


def _split_into_messages(lines: list[str]) -> list[str]:
    """Group whole lines into messages, so a split never falls inside an HTML tag."""
    messages: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if _count_utf16_units(candidate) > _MESSAGE_LIMIT_UTF16_UNITS:
            messages.append(current.rstrip("\n"))
            current = line
        else:
            current = candidate
    messages.append(current)
    return messages


def _count_utf16_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // _UTF16_UNIT_BYTES


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
