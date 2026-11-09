"""Guard against a second bot instance on the same token (Telegram 409 Conflict)."""

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

from hq_access_bot.errors import FatalBotError

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

# Number of bytes msvcrt.locking holds: one byte is enough to mark the file as taken.
_LOCKED_BYTES = 1


class InstanceAlreadyRunningError(FatalBotError):
    """Another bot instance already holds the lock."""


@contextmanager
def hold_instance_lock(lock_path: Path) -> Iterator[None]:
    """Hold an exclusive lock on the file for the duration of the block.

    Raises:
        InstanceAlreadyRunningError: another instance holds the lock.
    """
    with lock_path.open("w") as lock_file:
        try:
            _lock_exclusively(lock_file)
        except OSError as error:
            raise InstanceAlreadyRunningError(
                "Another bot instance is already running. Exiting."
            ) from error
        yield


def _lock_exclusively(lock_file: TextIO) -> None:
    if sys.platform == "win32":
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, _LOCKED_BYTES)
    else:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
