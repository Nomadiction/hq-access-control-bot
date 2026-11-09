"""All bot messages, in Telegram HTML markup."""

from html import escape

from hq_access_bot.whitelist.models import AddOutcome, Member, Person, Whitelist

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
        f"<i>Группа убрана из списка доступа.</i>"
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


def format_add_report(project: str, outcome: AddOutcome) -> str:
    lines = [f"<b>{_escape(project)}</b>"]
    if outcome.added:
        lines.append("✅ Добавлено: " + _escape(", ".join(outcome.added)))
    if outcome.skipped:
        lines.append("⏭ Уже были: " + _escape(", ".join(outcome.skipped)))
    return "\n".join(lines)


def format_removal_report(project: str, removed: list[str]) -> str:
    if removed:
        return f"<b>{_escape(project)}</b>\n🗑 Удалено: " + _escape(", ".join(removed))
    return f"<b>{_escape(project)}</b>\nНикого не нашёл для удаления."


def format_group_deleted_reply(project: str) -> str:
    return f"🗑 Группа <b>{_escape(project)}</b> убрана из списка доступа."


def format_access_lists(whitelist: Whitelist) -> str:
    blocks = []
    for group in whitelist.groups.values():
        member_lines = [_format_member_line(m) for m in group.members] or ["<i>пусто</i>"]
        blocks.append("\n".join([f"<b>{_escape(group.project)}</b>", *member_lines]))
    return "📋 <b>Списки доступа</b>\n\n" + "\n\n".join(blocks)


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
