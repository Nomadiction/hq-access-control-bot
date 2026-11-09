"""Access list storage in a JSON file."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from hq_access_bot.errors import FatalBotError
from hq_access_bot.whitelist.codec import WhitelistFormatError, dump_whitelist, parse_whitelist
from hq_access_bot.whitelist.models import Whitelist

_REPLACE_RETRIES = 5
_REPLACE_RETRY_PAUSE_SECONDS = 0.05


class WhitelistCorruptedError(FatalBotError):
    """The list file is unreadable. Overwriting it would lose the data, so it stays as is."""


class WhitelistStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._write_lock = asyncio.Lock()

    def read(self) -> Whitelist:
        """Read the current list; manual edits to the file are visible without a restart.

        Raises:
            WhitelistCorruptedError: the file cannot be parsed.
        """
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return parse_whitelist(raw)
        except FileNotFoundError:
            return Whitelist()
        except (json.JSONDecodeError, WhitelistFormatError) as error:
            raise WhitelistCorruptedError(f"{self._path} is corrupted: {error!r}") from error

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Whitelist]:
        """Yield the list for changes and save it on exit without an exception.

        Changes run strictly one at a time. Network calls inside the block would hold up
        the other writers, so make them after it exits.
        """
        async with self._write_lock:
            whitelist = self.read()
            yield whitelist
            await self._write(whitelist)

    async def _write(self, whitelist: Whitelist) -> None:
        payload = json.dumps(dump_whitelist(whitelist), ensure_ascii=False, indent=2) + "\n"
        temporary_path = self._path.with_name(self._path.name + ".tmp")
        temporary_path.write_text(payload, encoding="utf-8")
        await _replace_file(temporary_path, self._path)


async def _replace_file(source: Path, target: Path) -> None:
    """Replace the file atomically; Windows refuses while antivirus or an indexer holds it."""
    for _ in range(_REPLACE_RETRIES):
        try:
            source.replace(target)
            return
        except PermissionError:
            await asyncio.sleep(_REPLACE_RETRY_PAUSE_SECONDS)
    source.replace(target)
