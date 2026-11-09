"""Shared test tools: a fake Telegram network and builders for incoming updates."""

from collections.abc import AsyncGenerator, Callable
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import (
    ClientDecodeError,
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)
from aiogram.methods import GetChatMember, GetMe, TelegramMethod
from aiogram.types import ChatMemberLeft, ChatMemberMember, ChatMemberRestricted, User

ADMIN_ID = 111
BOT_ID = 123456
GROUP_ID = -1001
GROUP_KEY = str(GROUP_ID)
ALICE_RECORD = {"id": 10, "username": "alice", "in": True, "name": "Alice"}
FAKE_TOKEN = f"{BOT_ID}:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

_ADMIN_RIGHTS = {
    "can_invite_users": True,
    **dict.fromkeys(
        (
            "can_be_edited",
            "is_anonymous",
            "can_manage_chat",
            "can_delete_messages",
            "can_manage_video_chats",
            "can_restrict_members",
            "can_promote_members",
            "can_change_info",
            "can_post_stories",
            "can_edit_stories",
            "can_delete_stories",
            "can_send_welcome_messages",
        ),
        False,
    ),
}

_RESTRICTIONS = {
    "until_date": 0,
    "is_member": True,
    **dict.fromkeys(
        (
            "can_send_messages",
            "can_send_audios",
            "can_send_documents",
            "can_send_photos",
            "can_send_videos",
            "can_send_video_notes",
            "can_send_voice_notes",
            "can_send_polls",
            "can_send_other_messages",
            "can_add_web_page_previews",
            "can_react_to_messages",
            "can_edit_tag",
            "can_change_info",
            "can_invite_users",
            "can_pin_messages",
            "can_manage_topics",
        ),
        False,
    ),
}

ErrorFactory = Callable[[TelegramMethod[Any]], Exception]


def retry_after(seconds: int) -> ErrorFactory:
    return lambda method: TelegramRetryAfter(method=method, message="flood", retry_after=seconds)


def network_failure() -> ErrorFactory:
    return lambda method: TelegramNetworkError(method=method, message="network down")


def server_error() -> ErrorFactory:
    return lambda method: TelegramServerError(method=method, message="bad gateway")


def decode_error() -> ErrorFactory:
    return lambda method: ClientDecodeError("not json", ValueError("html"), "<html>")


def bad_request(message: str) -> ErrorFactory:
    return lambda method: TelegramBadRequest(method=method, message=message)


def unauthorized() -> ErrorFactory:
    return lambda method: TelegramUnauthorizedError(method=method, message="bad token")


class RecordingSession(BaseSession):
    """Records Bot API calls instead of going to the network."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self.failing_methods: set[type[TelegramMethod[Any]]] = set()
        self.chat_members: dict[int, tuple[str, str | None]] = {}
        self._scripted_errors: dict[type[TelegramMethod[Any]], list[ErrorFactory]] = {}

    def script_errors(
        self, method_type: type[TelegramMethod[Any]], *factories: ErrorFactory
    ) -> None:
        """Make the next calls of a method fail, one error per call, then succeed."""
        self._scripted_errors.setdefault(method_type, []).extend(factories)

    async def close(self) -> None:
        return None

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        yield b""

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ) -> Any:
        if not isinstance(method, GetMe):
            self.calls.append(method)
        scripted = self._scripted_errors.get(type(method))
        if scripted:
            raise scripted.pop(0)(method)
        if isinstance(method, GetMe):
            return User(id=BOT_ID, is_bot=True, first_name="bot", username="test_bot")
        if type(method) in self.failing_methods:
            raise TelegramBadRequest(method=method, message="forced failure")
        if isinstance(method, GetChatMember):
            return self._build_chat_member(method)
        return True

    def _build_chat_member(self, method: GetChatMember) -> Any:
        if method.user_id not in self.chat_members:
            raise TelegramBadRequest(method=method, message="user not found")
        status, username = self.chat_members[method.user_id]
        user = User(id=method.user_id, is_bot=False, first_name="Seen", username=username)
        if status == "member":
            return ChatMemberMember(user=user)
        if status == "restricted_left":
            return ChatMemberRestricted(user=user, **{**_RESTRICTIONS, "is_member": False})
        return ChatMemberLeft(user=user)


def make_user(user_id: int, username: str | None = None, first_name: str = "User") -> dict:
    user = {"id": user_id, "is_bot": False, "first_name": first_name}
    return {**user, "username": username} if username else user


BOT_USER = make_user(BOT_ID, "test_bot")
STRANGER = make_user(99, "bob", "Bob")


def private_chat(user_id: int) -> dict:
    return {"id": user_id, "type": "private", "first_name": "chat"}


def supergroup(chat_id: int = GROUP_ID, title: str = "Alpha") -> dict:
    return {"id": chat_id, "type": "supergroup", "title": title}


def basic_group(title: str = "Basic") -> dict:
    return {"id": -55, "type": "group", "title": title}


def channel() -> dict:
    return {"id": -1007, "type": "channel", "title": "News"}


def join_request(user: dict, chat: dict | None = None, user_chat_id: int | None = None) -> dict:
    return {
        "chat_join_request": {
            "chat": chat or supergroup(),
            "from": user,
            "user_chat_id": user_chat_id or user["id"],
            "date": 1,
        }
    }


def _build_member_state(status: str, user: dict) -> dict:
    if status == "restricted_left":
        return {**_build_member_state("restricted", user), "is_member": False}
    state: dict[str, Any] = {"status": status, "user": user}
    if status == "kicked":
        state["until_date"] = 0
    if status == "administrator":
        state.update(_ADMIN_RIGHTS)
    if status == "restricted":
        state.update(_RESTRICTIONS)
    return state


def _build_status_change(kind: str, old: str, new: str, user: dict, chat: dict | None) -> dict:
    return {
        kind: {
            "chat": chat or supergroup(),
            "from": make_user(ADMIN_ID),
            "date": 1,
            "old_chat_member": _build_member_state(old, user),
            "new_chat_member": _build_member_state(new, user),
        }
    }


def member_change(old: str, new: str, user: dict, chat: dict | None = None) -> dict:
    return _build_status_change("chat_member", old, new, user, chat)


def bot_change(
    old: str, new: str, chat: dict | None = None, *, can_invite_users: bool = True
) -> dict:
    update = _build_status_change("my_chat_member", old, new, BOT_USER, chat)
    if new == "administrator":
        update["my_chat_member"]["new_chat_member"]["can_invite_users"] = can_invite_users
    return update


def command(
    text: str, sender: dict | None = None, chat: dict | None = None, message_id: int = 7
) -> dict:
    sender = sender or make_user(ADMIN_ID, "root")
    return {
        "message": {
            "message_id": message_id,
            "date": 1,
            "chat": chat or private_chat(sender["id"]),
            "from": sender,
            "text": text,
        }
    }


def group_renamed(title: str, chat: dict | None = None) -> dict:
    return {
        "message": {
            "message_id": 8,
            "date": 1,
            "chat": chat or supergroup(),
            "from": make_user(ADMIN_ID, "root"),
            "new_chat_title": title,
        }
    }
