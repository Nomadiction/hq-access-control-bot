"""Process settings: reading .env and the environment, data file locations."""

import os
from dataclasses import dataclass
from pathlib import Path

from aiogram.utils.token import TokenValidationError, validate_token

from hq_access_bot.errors import FatalBotError

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"
DATA_DIR = _PROJECT_ROOT / "data"


class ConfigurationError(FatalBotError):
    """A setting is missing or malformed, so the process must not start."""


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    support_username: str


@dataclass(frozen=True, slots=True)
class DataPaths:
    whitelist: Path
    audit_log: Path
    instance_lock: Path

    @classmethod
    def inside(cls, data_dir: Path) -> "DataPaths":
        return cls(
            whitelist=data_dir / "whitelist.json",
            audit_log=data_dir / "access.log",
            instance_lock=data_dir / "hqbot.lock",
        )


def load_settings(env_path: Path = _ENV_PATH) -> Settings:
    """Build the settings; environment variables take precedence over .env.

    Raises:
        ConfigurationError: BOT_TOKEN or SUPPORT_USERNAME is missing, the token is malformed,
            or ADMIN_IDS is not numeric.
    """
    values = {**_read_dotenv(env_path), **os.environ}
    return Settings(
        bot_token=_parse_bot_token(values),
        admin_ids=_parse_admin_ids(values.get("ADMIN_IDS", "")),
        support_username=_require(values, "SUPPORT_USERNAME").lstrip("@"),
    )


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _require(values: dict[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise ConfigurationError(f"{key} is empty. Set it in .env or the environment.")
    return value


def _parse_bot_token(values: dict[str, str]) -> str:
    token = _require(values, "BOT_TOKEN")
    try:
        validate_token(token)
    except TokenValidationError as error:
        raise ConfigurationError("BOT_TOKEN is malformed.") from error
    return token


def _parse_admin_ids(raw: str) -> frozenset[int]:
    try:
        return frozenset(int(part) for part in raw.replace(" ", "").split(",") if part)
    except ValueError as error:
        raise ConfigurationError(f"ADMIN_IDS must be a list of numbers: {raw!r}") from error
