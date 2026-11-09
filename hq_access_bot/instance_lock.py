"""Guard against a second bot instance on the same token (Telegram 409 Conflict)."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # not available on Windows
    fcntl = None


class InstanceAlreadyRunningError(Exception):
    """Another bot instance already holds the lock."""


@contextmanager
def hold_instance_lock(lock_path: Path) -> Iterator[None]:
    """Hold a file lock for the duration of the block. Skipped on Windows."""
    if fcntl is None:
        yield
        return
    with lock_path.open("w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise InstanceAlreadyRunningError(
                "Another bot instance is already running. Exiting."
            ) from error
        yield
