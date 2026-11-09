"""Domain model of the access list, free of Telegram and file concerns."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from hq_access_bot.whitelist.identity import MemberRef, ObservedMember, Person


@dataclass(slots=True)
class Member:
    """An access list entry. has_joined means the person has actually been in the group."""

    user_id: int | None = None
    username: str | None = None
    has_joined: bool = False
    full_name: str | None = None

    @property
    def ref(self) -> MemberRef:
        return MemberRef(self.user_id, self.username)

    @property
    def identity(self) -> int | str | None:
        """Uniqueness key of the entry: the id, or the username until the id is known."""
        return self.user_id if self.user_id is not None else self.username

    def matches(self, ref: MemberRef) -> bool:
        """Check this entry against a reference.

        When the id is known on both sides it alone decides: a freed username can be taken
        by someone else, and a matching username must not grant that person access.
        """
        if self.user_id is not None and ref.user_id is not None:
            return self.user_id == ref.user_id
        return ref.username is not None and self.username == ref.username

    def is_outdated_for(self, person: Person) -> bool:
        canonical_username = person.ref.username
        return (
            self.user_id != person.user_id
            or not self.has_joined
            or (canonical_username is not None and self.username != canonical_username)
        )

    def has_departed(self, observation: ObservedMember | None) -> bool:
        """True only for an entry that had joined and is now observed outside the group."""
        return observation is not None and not observation.is_in_group and self.has_joined

    def confirm(self, person: Person) -> None:
        """Bind the entry to the person who joined; a missing username keeps the old one."""
        self.user_id = person.user_id
        self.has_joined = True
        self.full_name = person.full_name
        if person.ref.username:
            self.username = person.ref.username

    def apply_observation(self, person: Person) -> None:
        """Apply a direct Telegram answer, where a missing username is also reliable."""
        self.has_joined = True
        self.username = person.ref.username
        if person.full_name:
            self.full_name = person.full_name


@dataclass(frozen=True, slots=True)
class MemberChange:
    """Labels of the members an operation changed and of those it left as they were."""

    applied: list[str]
    skipped: list[str]


@dataclass(slots=True)
class Group:
    project: str
    _members: list[Member] = field(default_factory=list)

    @property
    def members(self) -> tuple[Member, ...]:
        return tuple(self._members)

    def has_member(self, person: Person) -> bool:
        return self._find_member(person) is not None

    def needs_confirmation(self, person: Person) -> bool:
        member = self._find_member(person)
        return member is not None and member.is_outdated_for(person)

    def confirm_member(self, person: Person) -> None:
        member = self._find_member(person)
        if member is None:
            return
        member.confirm(person)
        self._members = [m for m in self._members if m is member or not m.matches(member.ref)]

    def add_all(self, refs: Iterable[MemberRef]) -> MemberChange:
        added, skipped = [], []
        for ref in refs:
            if any(m.matches(ref) for m in self._members):
                skipped.append(ref.label)
            else:
                self._members.append(Member(user_id=ref.user_id, username=ref.username))
                added.append(ref.label)
        return MemberChange(added, skipped)

    def remove_all(self, refs: Iterable[MemberRef]) -> MemberChange:
        removed, skipped = [], []
        for ref in refs:
            matched = [m.ref.label for m in self._members if m.matches(ref)]
            removed += matched
            if not matched:
                skipped.append(ref.label)
            self._members = [m for m in self._members if not m.matches(ref)]
        return MemberChange(removed, skipped)

    def reconcile(self, observed: Mapping[int, ObservedMember]) -> None:
        """Bring the list in line with the actual group membership.

        Members that could not be checked and entries not used yet are left alone.
        Username-only entries are also dropped when that username belongs to someone
        who left or is already recorded on a member with an id.
        """
        kept, departed_usernames = self._apply_observations(observed)
        bound_usernames = {m.username for m in kept if m.user_id is not None and m.username}
        redundant_usernames = departed_usernames | bound_usernames
        self._members = [
            m for m in kept if m.user_id is not None or m.username not in redundant_usernames
        ]

    def _find_member(self, person: Person) -> Member | None:
        return next((m for m in self._members if m.matches(person.ref)), None)

    def _apply_observations(
        self, observed: Mapping[int, ObservedMember]
    ) -> tuple[list[Member], set[str]]:
        kept: list[Member] = []
        departed_usernames: set[str] = set()
        for member in self._members:
            observation = observed.get(member.user_id) if member.user_id is not None else None
            if member.has_departed(observation):
                departed_usernames |= {observation.person.ref.username, member.username} - {None}
                continue
            if observation is not None and observation.is_in_group:
                member.apply_observation(observation.person)
            kept.append(member)
        return kept, departed_usernames


@dataclass(slots=True)
class Whitelist:
    """All tracked groups, keyed by the group's chat_id as a string."""

    _groups: dict[str, Group] = field(default_factory=dict)

    @property
    def groups(self) -> Mapping[str, Group]:
        return MappingProxyType(self._groups)

    def find_group_key(self, target: str) -> str | None:
        """Find a group by chat_id or by project name, case-insensitively."""
        if target in self._groups:
            return target
        lowered = target.lower()
        return next((k for k, g in self._groups.items() if g.project.lower() == lowered), None)

    def find_group(self, target: str) -> Group | None:
        key = self.find_group_key(target)
        return self._groups[key] if key is not None else None

    def register_group(self, chat_key: str, project: str) -> bool:
        """Create an empty group. Returns False if it already exists."""
        if chat_key in self._groups:
            return False
        self._groups[chat_key] = Group(project)
        return True

    def remove_group(self, chat_key: str) -> Group | None:
        return self._groups.pop(chat_key, None)

    def confirm_member(self, chat_key: str, person: Person) -> None:
        group = self._groups.get(chat_key)
        if group is not None:
            group.confirm_member(person)

    def reconcile(self, observed: Mapping[str, Mapping[int, ObservedMember]]) -> None:
        for chat_key, group in self._groups.items():
            group.reconcile(observed.get(chat_key, {}))

    def count_unique_members(self) -> int:
        return len({m.identity for group in self._groups.values() for m in group.members})
