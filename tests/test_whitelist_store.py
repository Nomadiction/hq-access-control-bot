import json
from pathlib import Path

import pytest

from hq_access_bot.whitelist import store as store_module
from hq_access_bot.whitelist.codec import dump_whitelist, parse_whitelist
from hq_access_bot.whitelist.models import Group, Member
from hq_access_bot.whitelist.store import WhitelistCorruptedError, WhitelistStore


@pytest.fixture
def path(tmp_path):
    return tmp_path / "whitelist.json"


@pytest.fixture
def store(path):
    return WhitelistStore(path)


def test_codec_keeps_every_member_field_through_a_round_trip():
    raw = {
        "-1": {
            "project": "Project",
            "members": [{"id": 1, "username": "a", "in": True, "name": "Name"}, {"username": "b"}],
        }
    }

    assert dump_whitelist(parse_whitelist(raw)) == raw


def test_codec_normalizes_usernames_and_trims_names():
    raw = {"-1": {"project": "A", "members": [{"username": "@ABC", "name": "  N  "}]}}

    assert parse_whitelist(raw).groups["-1"].members == [Member(username="abc", full_name="N")]


def test_codec_merges_duplicate_members():
    raw = {
        "-1": {
            "project": "A",
            "members": [{"id": 1}, {"id": 1, "in": True}, {"username": "b"}, {"username": "B"}],
        }
    }

    assert parse_whitelist(raw).groups["-1"].members == [
        Member(user_id=1),
        Member(username="b"),
    ]


def test_missing_file_reads_as_empty_whitelist(store):
    assert store.read().groups == {}


@pytest.mark.parametrize(
    "content",
    [
        "{ broken",
        '{"-1": {"project": "A"}}',
        '{"-1": {"project": "A", "members": [{"name": "nobody"}]}}',
        '{"-1": {"project": "A", "ids": [1]}}',
    ],
)
def test_unreadable_file_raises_instead_of_reading_empty(store, path, content):
    path.write_text(content, encoding="utf-8")

    with pytest.raises(WhitelistCorruptedError):
        store.read()


async def test_transaction_refuses_to_overwrite_corrupted_file(store, path):
    path.write_text("{ broken", encoding="utf-8")

    with pytest.raises(WhitelistCorruptedError):
        async with store.transaction():
            pass

    assert path.read_text(encoding="utf-8") == "{ broken"


async def test_transaction_persists_changes(store, path):
    async with store.transaction() as whitelist:
        whitelist.groups["-1"] = Group("A", [Member(user_id=1)])

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "-1": {"project": "A", "members": [{"id": 1}]}
    }
    assert list(path.parent.iterdir()) == [path]


async def test_cyrillic_is_stored_readable(store, path):
    async with store.transaction() as whitelist:
        whitelist.groups["-1"] = Group("Проект")

    assert "Проект" in path.read_text(encoding="utf-8")


async def test_failed_transaction_changes_nothing(store, path):
    async with store.transaction() as whitelist:
        whitelist.groups["-1"] = Group("A")

    with pytest.raises(RuntimeError):
        async with store.transaction() as whitelist:
            whitelist.groups["-2"] = Group("B")
            raise RuntimeError

    assert set(json.loads(path.read_text(encoding="utf-8"))) == {"-1"}


@pytest.fixture
def no_retry_pause(monkeypatch):
    monkeypatch.setattr(store_module, "_REPLACE_RETRY_PAUSE_SECONDS", 0)


async def test_replace_is_retried_while_file_is_locked(store, path, monkeypatch, no_retry_pause):
    real_replace = Path.replace
    failures = iter([True, True, False])

    def flaky_replace(self, target):
        if next(failures):
            raise PermissionError
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    async with store.transaction() as whitelist:
        whitelist.groups["-1"] = Group("A")

    assert "-1" in json.loads(path.read_text(encoding="utf-8"))


async def test_replace_gives_up_and_keeps_old_file(store, path, monkeypatch, no_retry_pause):
    path.write_text("{}", encoding="utf-8")

    def locked_replace(self, target):
        raise PermissionError

    monkeypatch.setattr(Path, "replace", locked_replace)

    with pytest.raises(PermissionError):
        async with store.transaction() as whitelist:
            whitelist.groups["-1"] = Group("A")

    assert path.read_text(encoding="utf-8") == "{}"
