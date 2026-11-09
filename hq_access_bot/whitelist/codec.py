"""Conversion of the access list to and from the JSON file structure."""

from typing import Any

from hq_access_bot.whitelist.identity import normalize_username
from hq_access_bot.whitelist.models import Group, Member, Whitelist


class WhitelistFormatError(ValueError):
    """The JSON is well formed but does not describe an access list."""


def parse_whitelist(raw: Any) -> Whitelist:
    """Parse the contents of whitelist.json.

    Raises:
        WhitelistFormatError: the structure is invalid.
    """
    if not isinstance(raw, dict):
        raise WhitelistFormatError("the top level must be an object")
    return Whitelist({key: _parse_group_entry(key, group) for key, group in raw.items()})


def dump_whitelist(whitelist: Whitelist) -> dict[str, Any]:
    return {key: _dump_group(group) for key, group in whitelist.groups.items()}


def _parse_group_entry(key: str, raw: dict[str, Any]) -> Group:
    try:
        int(key)
        return _parse_group(raw)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise WhitelistFormatError(f"group {key}: {error!r}") from error


def _parse_group(raw: dict[str, Any]) -> Group:
    project = raw["project"]
    if not isinstance(project, str) or not project.strip():
        raise ValueError(f"project must be a non-empty string: {project!r}")
    raw_members = raw["members"]
    if not isinstance(raw_members, list):
        raise ValueError(f"members must be a list: {raw_members!r}")
    members: dict[Any, Member] = {}
    for raw_member in raw_members:
        member = _parse_member(raw_member)
        members.setdefault(member.identity, member)
    return Group(project, list(members.values()), is_active=not _read_flag(raw, "inactive"))


def _parse_member(raw: dict[str, Any]) -> Member:
    user_id = raw.get("id")
    if user_id is not None and (isinstance(user_id, bool) or not isinstance(user_id, int)):
        raise ValueError(f"id must be a number: {user_id!r}")
    username = normalize_username(raw.get("username"))
    if user_id is None and username is None:
        raise ValueError(f"Member has neither id nor username: {raw}")
    return Member(
        user_id=user_id,
        username=username,
        has_joined=_read_flag(raw, "in"),
        full_name=(raw.get("name") or "").strip() or None,
    )


def _read_flag(raw: dict[str, Any], key: str) -> bool:
    value = raw.get(key, False)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be true or false: {value!r}")
    return value


def _dump_group(group: Group) -> dict[str, Any]:
    dumped: dict[str, Any] = {
        "project": group.project,
        "members": [_dump_member(m) for m in group.members],
    }
    if not group.is_active:
        dumped["inactive"] = True
    return dumped


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
