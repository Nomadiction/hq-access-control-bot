"""Parsing of admin command arguments."""

from hq_access_bot.whitelist.identity import MemberRef, normalize_username
from hq_access_bot.whitelist.models import Whitelist


def parse_target_and_members(args: str | None, whitelist: Whitelist) -> tuple[str, list[MemberRef]]:
    """Split arguments into a target (project name or chat_id) and members.

    Members are the trailing tokens of the form @username or a positive number.
    Everything before them is the project name, which may span several words.
    A project name can itself end in a number, so the longest prefix naming a known
    group wins: with a group "Test 2", "Test 2 @a" targets that group.
    """
    tokens = (args or "").split()
    boundary = _find_target_end(tokens, whitelist)
    refs = [ref for token in tokens[boundary:] if (ref := _parse_member_token(token))]
    return " ".join(tokens[:boundary]), refs


def _find_target_end(tokens: list[str], whitelist: Whitelist) -> int:
    first_member = len(tokens)
    while first_member > 0 and _is_member_token(tokens[first_member - 1]):
        first_member -= 1
    for end in range(len(tokens), first_member, -1):
        if whitelist.find_group_key(" ".join(tokens[:end])) is not None:
            return end
    return first_member


def _is_member_token(token: str) -> bool:
    return token.startswith("@") or token.isdigit()


def _parse_member_token(token: str) -> MemberRef | None:
    if token.isdigit():
        return MemberRef(user_id=int(token))
    username = normalize_username(token)
    return MemberRef(username=username) if username else None
