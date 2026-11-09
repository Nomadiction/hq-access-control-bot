"""Value types that say who a person is, as Telegram and admin commands name them."""

from dataclasses import dataclass


def normalize_username(raw: str | None) -> str | None:
    """Normalize a username for storage: no @, lowercase, empty becomes None."""
    return (raw or "").lstrip("@").lower() or None


@dataclass(frozen=True, slots=True)
class MemberRef:
    """Reference to a member by id, by username, or by both."""

    user_id: int | None = None
    username: str | None = None

    @property
    def label(self) -> str:
        return f"@{self.username}" if self.username else f"id {self.user_id}"


@dataclass(frozen=True, slots=True)
class Person:
    """A Telegram user as reported by the API, with the username in its original case."""

    user_id: int
    username: str | None
    full_name: str

    @property
    def ref(self) -> MemberRef:
        return MemberRef(self.user_id, normalize_username(self.username))


@dataclass(frozen=True, slots=True)
class ObservedMember:
    """What Telegram answered when asked about a member of a group."""

    person: Person
    is_in_group: bool
    was_joined: bool
