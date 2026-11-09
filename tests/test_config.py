import pytest

from hq_access_bot.config import ConfigurationError, DataPaths, load_settings

ENV_KEYS = ("BOT_TOKEN", "ADMIN_IDS", "SUPPORT_USERNAME")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text("BOT_TOKEN=1:file\nSUPPORT_USERNAME=help\n", encoding="utf-8")
    return path


def test_reads_values_from_dotenv_ignoring_comments_and_quotes(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "# comment\n\nBOT_TOKEN=\"1:quoted\"\nADMIN_IDS=1, 2\nSUPPORT_USERNAME='@help'\n",
        encoding="utf-8",
    )

    settings = load_settings(path)

    assert settings.bot_token == "1:quoted"
    assert settings.admin_ids == {1, 2}
    assert settings.support_username == "help"


def test_environment_overrides_dotenv(env_file, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "2:env")

    assert load_settings(env_file).bot_token == "2:env"


def test_missing_dotenv_is_allowed_when_environment_is_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "1:t")
    monkeypatch.setenv("SUPPORT_USERNAME", "s")

    assert load_settings(tmp_path / "absent").admin_ids == frozenset()


@pytest.mark.parametrize("missing_key", ["BOT_TOKEN", "SUPPORT_USERNAME"])
def test_missing_required_value_names_the_key(tmp_path, monkeypatch, missing_key):
    for key in {"BOT_TOKEN", "SUPPORT_USERNAME"} - {missing_key}:
        monkeypatch.setenv(key, "1:value")

    with pytest.raises(ConfigurationError, match=missing_key):
        load_settings(tmp_path / "absent")


def test_placeholder_token_is_rejected_without_echoing_it(env_file, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "PASTE_TOKEN_FROM_BOTFATHER")

    with pytest.raises(ConfigurationError, match="BOT_TOKEN") as caught:
        load_settings(env_file)

    assert "PASTE" not in str(caught.value)


def test_non_numeric_admin_ids_are_rejected(env_file, monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "12,abc")

    with pytest.raises(ConfigurationError, match="ADMIN_IDS"):
        load_settings(env_file)


def test_data_paths_live_inside_given_directory(tmp_path):
    paths = DataPaths.inside(tmp_path)

    assert {paths.whitelist.parent, paths.audit_log.parent, paths.instance_lock.parent} == {
        tmp_path
    }
