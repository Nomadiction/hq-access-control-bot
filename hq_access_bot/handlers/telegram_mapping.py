"""Translation of Telegram types and statuses into domain concepts."""

from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import Chat, ChatMember, ChatMemberRestricted, User

from hq_access_bot.whitelist.identity import Person

DEPARTED_STATUSES = frozenset({ChatMemberStatus.LEFT, ChatMemberStatus.KICKED})
PRESENT_STATUSES = frozenset(
    {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
)


def is_admin_in_private_chat(chat: Chat, user: User, admin_ids: frozenset[int]) -> bool:
    """Admin tools show member lists, so they stay out of group chats."""
    return chat.type == ChatType.PRIVATE and user.id in admin_ids


def is_present_in_chat(chat_member: ChatMember) -> bool:
    """Tell whether the user is in the chat; a restricted user may already have left it."""
    if isinstance(chat_member, ChatMemberRestricted):
        return chat_member.is_member
    return chat_member.status not in DEPARTED_STATUSES


def build_project_name(title: str | None, chat: Chat) -> str:
    """Name a project after its chat; the access list file requires a non-blank name."""
    return (title or "").strip() or str(chat.id)


def build_chat_key(chat: Chat) -> str:
    """Key of a chat in the access list: its id as a string, like any JSON object key."""
    return str(chat.id)


def build_person(user: User) -> Person:
    return Person(user_id=user.id, username=user.username, full_name=user.full_name)
