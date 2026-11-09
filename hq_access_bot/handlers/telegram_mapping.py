"""Translation of Telegram types and statuses into domain concepts."""

from aiogram.enums import ChatMemberStatus
from aiogram.types import Chat, User

from hq_access_bot.whitelist.identity import Person

DEPARTED_STATUSES = frozenset({ChatMemberStatus.LEFT, ChatMemberStatus.KICKED})
PRESENT_STATUSES = frozenset(
    {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
)


def build_chat_key(chat: Chat) -> str:
    """Key of a chat in the access list: its id as a string, like any JSON object key."""
    return str(chat.id)


def build_person(user: User) -> Person:
    return Person(user_id=user.id, username=user.username, full_name=user.full_name)
