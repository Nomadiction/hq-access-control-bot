"""Parsing of admin command arguments."""

import re
from dataclasses import dataclass

from hq_access_bot.whitelist.identity import MemberRef, normalize_username
from hq_access_bot.whitelist.models import Whitelist

# Telegram usernames: a letter, then letters, digits or underscores, 4 to 32 characters in total.
_USERNAME_PATTERN = re.compile(r"[a-z][a-z0-9_]{3,31}")


@dataclass(frozen=True, slots=True)
class MemberCommandArgs:
    target: str
    refs: list[MemberRef]
    invalid: list[str]


def parse_target_and_members(args: str | None, whitelist: Whitelist) -> MemberCommandArgs:
    """Split arguments into a target (project name or chat_id) and members.

    Members are the trailing tokens of the form @username or a positive number, separated
    by spaces or commas. Everything before them is the project name, which may span several
    words. A project name can itself end in a number, so the longest prefix naming a known
    group wins: with a group "Test 2", "Test 2 @anna" targets that group.
    """
    tokens = (args or "").split()
    boundary = _find_target_end(tokens, whitelist)
    refs, invalid = _parse_member_tokens(tokens[boundary:])
    return MemberCommandArgs(_join_target(tokens[:boundary]), refs, invalid)


def parse_members(text: str) -> tuple[list[MemberRef], list[str]]:
    """Read members separated by spaces or commas. Returns them and the unreadable pieces."""
    return _parse_member_tokens(text.split())


def _parse_member_tokens(tokens: list[str]) -> tuple[list[MemberRef], list[str]]:
    refs: list[MemberRef] = []
    invalid: list[str] = []
    for piece in (piece for token in tokens for piece in _split_pieces(token)):
        ref = _parse_member_piece(piece)
        if ref is None:
            invalid.append(piece)
        else:
            refs.append(ref)
    return refs, invalid


def _find_target_end(tokens: list[str], whitelist: Whitelist) -> int:
    first_member = len(tokens)
    while first_member > 0 and _is_member_token(tokens[first_member - 1]):
        first_member -= 1
    for end in range(len(tokens), first_member, -1):
        if whitelist.find_group_keys(_join_target(tokens[:end])):
            return end
    return first_member


def _join_target(tokens: list[str]) -> str:
    return " ".join(tokens).rstrip(",")


def _split_pieces(token: str) -> list[str]:
    return [piece for piece in token.split(",") if piece]


def _is_member_token(token: str) -> bool:
    return all(piece.startswith("@") or _is_number(piece) for piece in _split_pieces(token))


def _is_number(piece: str) -> bool:
    return piece.isascii() and piece.isdigit()


def _parse_member_piece(piece: str) -> MemberRef | None:
    if _is_number(piece):
        return MemberRef(user_id=int(piece))
    username = normalize_username(piece)
    if username is not None and _USERNAME_PATTERN.fullmatch(username):
        return MemberRef(username=username)
    return None
