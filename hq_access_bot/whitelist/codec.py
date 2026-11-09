"""Conversion of the access list to and from the JSON file structure."""

from typing import Any

from hq_access_bot.whitelist.models import Group, Member, Whitelist, normalize_username


def parse_whitelist(raw: dict[str, Any]) -> Whitelist:
    """Parse the contents of whitelist.json.

    Raises:
        ValueError, KeyError, TypeError, AttributeError: the file structure is invalid.
    """
    return Whitelist({key: _parse_group(group) for key, group in raw.items()})


def dump_whitelist(whitelist: Whitelist) -> dict[str, Any]:
    return {
        key: {"project": group.project, "members": [_dump_member(m) for m in group.members]}
        for key, group in whitelist.groups.items()
    }


def _parse_group(raw: dict[str, Any]) -> Group:
    members: dict[Any, Member] = {}
    for raw_member in raw["members"]:
        member = _parse_member(raw_member)
        members.setdefault(member.identity, member)
    return Group(project=raw.get("project", ""), members=list(members.values()))


def _parse_member(raw: dict[str, Any]) -> Member:
    user_id = int(raw["id"]) if raw.get("id") is not None else None
    username = normalize_username(raw.get("username"))
    if user_id is None and username is None:
        raise ValueError(f"Member has neither id nor username: {raw}")
    return Member(
        user_id=user_id,
        username=username,
        has_joined=bool(raw.get("in")),
        full_name=(raw.get("name") or "").strip() or None,
    )


def _dump_member(member: Member) -> dict[str, Any]:
    dumped: dict[str, Any] = {}
    if member.user_id is not None:
        dumped["id"] = member.user_id
    if member.username:
        dumped["username"] = member.username
    if member.has_joined:
        dumped["in"] = True
    if member.full_name:
        dumped["name"] = member.full_name
    return dumped
