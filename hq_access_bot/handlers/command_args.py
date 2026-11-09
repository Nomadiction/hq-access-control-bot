"""Parsing of admin command arguments."""

from hq_access_bot.whitelist.models import MemberRef, normalize_username


def parse_target_and_members(args: str | None) -> tuple[str, list[MemberRef]]:
    """Split arguments into a target (project name or chat_id) and members.

    Members are the trailing tokens of the form @username or a positive number.
    Everything before them is the project name, which may span several words.
    """
    tokens = (args or "").split()
    boundary = len(tokens)
    while boundary > 0 and _is_member_token(tokens[boundary - 1]):
        boundary -= 1
    refs = [ref for token in tokens[boundary:] if (ref := _parse_member_token(token))]
    return " ".join(tokens[:boundary]), refs


def _is_member_token(token: str) -> bool:
    return token.startswith("@") or token.isdigit()


def _parse_member_token(token: str) -> MemberRef | None:
    if token.isdigit():
        return MemberRef(user_id=int(token))
    username = normalize_username(token)
    return MemberRef(username=username) if username else None
