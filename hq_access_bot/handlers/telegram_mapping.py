"""Translation of Telegram types and statuses into domain concepts."""

from aiogram.enums import ChatMemberStatus
from aiogram.types import User

from hq_access_bot.whitelist.models import Person

DEPARTED_STATUSES = frozenset({ChatMemberStatus.LEFT, ChatMemberStatus.KICKED})
PRESENT_STATUSES = frozenset(
    {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
)


def build_person(user: User) -> Person:
    return Person(user_id=user.id, username=user.username, full_name=user.full_name)
