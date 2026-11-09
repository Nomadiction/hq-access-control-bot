"""Access list storage in a JSON file."""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from hq_access_bot.errors import FatalBotError
from hq_access_bot.whitelist.codec import WhitelistFormatError, dump_whitelist, parse_whitelist
from hq_access_bot.whitelist.models import Whitelist

_REPLACE_RETRIES = 5
_REPLACE_RETRY_PAUSE_SECONDS = 0.05


class WhitelistCorruptedError(FatalBotError):
    """The list file is missing or unreadable, so no access decision can be trusted."""


class WhitelistStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._write_lock = asyncio.Lock()

    def create_if_missing(self) -> None:
        """Create an empty list unless the file is already there."""
        if not self._path.exists():
            _write_durably(self._path, _serialize(Whitelist()))

    def read(self) -> Whitelist:
        """Read the current list; manual edits to the file are visible without a restart.

        Raises:
            WhitelistCorruptedError: the file is missing or cannot be parsed.
        """
        try:
            text = self._path.read_text(encoding="utf-8-sig")
            return parse_whitelist(json.loads(text))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, WhitelistFormatError) as error:
            raise WhitelistCorruptedError(
                f"{self._path} is missing or corrupted: {error!r}"
            ) from error

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Whitelist]:
        """Yield the list for changes and save it on a clean exit, if anything changed.

        Changes run strictly one at a time. Network calls inside the block would hold up
        the other writers, so make them after it exits.
        """
        async with self._write_lock:
            whitelist = self.read()
            original = dump_whitelist(whitelist)
            yield whitelist
            if dump_whitelist(whitelist) != original:
                await self._write(whitelist)

    async def _write(self, whitelist: Whitelist) -> None:
        temporary_path = self._path.with_name(self._path.name + ".tmp")
        _write_durably(temporary_path, _serialize(whitelist))
        await _replace_file(temporary_path, self._path)


def _serialize(whitelist: Whitelist) -> str:
    return json.dumps(dump_whitelist(whitelist), ensure_ascii=False, indent=2) + "\n"


def _write_durably(path: Path, payload: str) -> None:
    """Flush to the device, so a power cut cannot leave a half-written file behind."""
    with path.open("w", encoding="utf-8") as file:
        file.write(payload)
        file.flush()
        os.fsync(file.fileno())


async def _replace_file(source: Path, target: Path) -> None:
    """Replace the file atomically; Windows refuses while antivirus or an indexer holds it."""
    for _ in range(_REPLACE_RETRIES):
        try:
            source.replace(target)
            return
        except PermissionError:
            await asyncio.sleep(_REPLACE_RETRY_PAUSE_SECONDS)
    source.replace(target)
