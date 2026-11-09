import json
from pathlib import Path

import pytest

from hq_access_bot.whitelist import store as store_module
from hq_access_bot.whitelist.codec import dump_whitelist, parse_whitelist
from hq_access_bot.whitelist.identity import MemberRef
from hq_access_bot.whitelist.models import Member
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

    assert list(parse_whitelist(raw).groups["-1"].members) == [
        Member(username="abc", full_name="N")
    ]


def test_codec_merges_duplicate_members():
    raw = {
        "-1": {
            "project": "A",
            "members": [{"id": 1}, {"id": 1, "in": True}, {"username": "b"}, {"username": "B"}],
        }
    }

    assert list(parse_whitelist(raw).groups["-1"].members) == [
        Member(user_id=1),
        Member(username="b"),
    ]


def test_missing_file_is_an_error(store):
    with pytest.raises(WhitelistCorruptedError, match=r"whitelist\.json"):
        store.read()


def test_path_that_cannot_be_read_is_an_error(tmp_path):
    with pytest.raises(WhitelistCorruptedError):
        WhitelistStore(tmp_path).read()


def test_first_run_creates_an_empty_list(store):
    store.create_if_missing()

    assert store.read().groups == {}


def test_creation_keeps_an_existing_list(store, path):
    path.write_text('{"-1": {"project": "A", "members": []}}', encoding="utf-8")

    store.create_if_missing()

    assert set(store.read().groups) == {"-1"}


def test_byte_order_mark_is_accepted(store, path):
    path.write_bytes(b"\xef\xbb\xbf" + b'{"-1": {"project": "A", "members": []}}')

    assert set(store.read().groups) == {"-1"}


def test_wrong_encoding_is_reported_as_corruption(store, path):
    path.write_bytes('{"-1": {"project": "Проект", "members": []}}'.encode("cp1251"))

    with pytest.raises(WhitelistCorruptedError):
        store.read()


@pytest.mark.parametrize(
    "content",
    [
        "{ broken",
        '{"-1": {"project": "A"}}',
        '{"-1": {"project": "A", "members": [{"name": "nobody"}]}}',
        '{"-1": {"project": "A", "ids": [1]}}',
        "[]",
        '{"abc": {"project": "A", "members": []}}',
        '{"-1": {"members": []}}',
        '{"-1": {"project": "  ", "members": []}}',
        '{"-1": {"project": 5, "members": []}}',
        '{"-1": {"project": "A", "members": [{"id": true}]}}',
        '{"-1": {"project": "A", "members": [{"id": "12"}]}}',
        '{"-1": {"project": "A", "members": 5}}',
        '{"-1": {"project": "A", "members": {}}}',
        '{"-1": {"project": "A", "members": ""}}',
        '{"-1": {"project": "A", "members": [], "inactive": "false"}}',
        '{"-1": {"project": "A", "members": [{"id": 1, "in": "false"}]}}',
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
    store.create_if_missing()
    async with store.transaction() as whitelist:
        whitelist.register_group("-1", "A")
        whitelist.groups["-1"].add_all([MemberRef(user_id=1)])

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "-1": {"project": "A", "members": [{"id": 1}]}
    }
    assert list(path.parent.iterdir()) == [path]


async def test_transaction_without_changes_leaves_the_file_alone(store, path):
    original = '{"-1":{"project":"A","members":[]}}'
    path.write_text(original, encoding="utf-8")

    async with store.transaction():
        pass

    assert path.read_text(encoding="utf-8") == original


async def test_data_reaches_the_disk_before_the_file_is_replaced(store, path, monkeypatch):
    path.write_text("{}", encoding="utf-8")
    events = []
    real_replace = Path.replace

    def recording_replace(self, target):
        events.append("replace")
        return real_replace(self, target)

    monkeypatch.setattr(store_module.os, "fsync", lambda fd: events.append("fsync"))
    monkeypatch.setattr(Path, "replace", recording_replace)

    async with store.transaction() as whitelist:
        whitelist.register_group("-1", "A")

    assert events == ["fsync", "replace"]


async def test_cyrillic_is_stored_readable(store, path):
    store.create_if_missing()
    async with store.transaction() as whitelist:
        whitelist.register_group("-1", "Проект")

    assert "Проект" in path.read_text(encoding="utf-8")


async def test_failed_transaction_changes_nothing(store, path):
    store.create_if_missing()

    async with store.transaction() as whitelist:
        whitelist.register_group("-1", "A")

    with pytest.raises(RuntimeError):
        async with store.transaction() as whitelist:
            whitelist.register_group("-2", "B")
            raise RuntimeError

    assert set(json.loads(path.read_text(encoding="utf-8"))) == {"-1"}


@pytest.fixture
def no_retry_pause(monkeypatch):
    monkeypatch.setattr(store_module, "_REPLACE_RETRY_PAUSE_SECONDS", 0)


async def test_replace_is_retried_while_file_is_locked(store, path, monkeypatch, no_retry_pause):
    store.create_if_missing()
    real_replace = Path.replace
    failures = iter([True, True, False])

    def flaky_replace(self, target):
        if next(failures):
            raise PermissionError
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    async with store.transaction() as whitelist:
        whitelist.register_group("-1", "A")

    assert "-1" in json.loads(path.read_text(encoding="utf-8"))


async def test_replace_gives_up_and_keeps_old_file(store, path, monkeypatch, no_retry_pause):
    path.write_text("{}", encoding="utf-8")

    def locked_replace(self, target):
        raise PermissionError

    monkeypatch.setattr(Path, "replace", locked_replace)

    with pytest.raises(PermissionError):
        async with store.transaction() as whitelist:
            whitelist.register_group("-1", "A")

    assert path.read_text(encoding="utf-8") == "{}"
