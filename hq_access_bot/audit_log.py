"""Access audit: a rotating file of who was let in and what changed, echoed to the console."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from hq_access_bot.whitelist.identity import Person

logger = logging.getLogger(__name__)

_RECORD_FORMAT = "%(asctime)s %(message)s"
_MAX_FILE_BYTES = 1_000_000
_ROTATED_FILES_KEPT = 3


class AuditLog:
    def __init__(self, path: Path) -> None:
        # Outside the logging registry, so records reach the console only through _write.
        self._file_logger = logging.Logger("access", logging.INFO)
        self._handler = RotatingFileHandler(
            path, maxBytes=_MAX_FILE_BYTES, backupCount=_ROTATED_FILES_KEPT, encoding="utf-8"
        )
        self._handler.setFormatter(logging.Formatter(_RECORD_FORMAT))
        self._file_logger.addHandler(self._handler)

    def close(self) -> None:
        self._handler.close()

    def record_request_approved(self, person: Person, project: str) -> None:
        self._record_request("APPROVED", person, project)

    def record_request_declined(self, person: Person, project: str) -> None:
        self._record_request("DECLINED", person, project)

    def record_request_approved_manually(self, user_id: int, project: str) -> None:
        self._record_by_id("APPROVED-MANUAL", user_id, project)

    def record_request_declined_manually(self, user_id: int, project: str) -> None:
        self._record_by_id("DECLINED-MANUAL", user_id, project)

    def record_request_failed(self, person: Person, project: str) -> None:
        self._record_request("REQUEST-FAILED", person, project)

    def record_member_unlisted(self, person: Person, project: str) -> None:
        self._record_request("MEMBER-UNLISTED", person, project)

    def record_member_kicked(self, user_id: int, project: str) -> None:
        self._record_by_id("KICK", user_id, project)

    def record_member_left_banned(self, user_id: int, project: str) -> None:
        self._record_by_id("KICK-STILL-BANNED", user_id, project)

    def record_member_left(self, person: Person, project: str, removed: list[str]) -> None:
        self._write("MEMBER-LEFT id=%s project=%s %s", person.user_id, project, ", ".join(removed))

    def record_members_added(self, project: str, added: list[str]) -> None:
        self._write("ADD project=%s %s", project, ", ".join(added))

    def record_members_removed(self, project: str, removed: list[str]) -> None:
        self._write("REMOVE project=%s %s", project, ", ".join(removed))

    def record_group_registered(self, chat_key: str, title: str) -> None:
        self._write("GROUP-ADDED %s «%s»", chat_key, title)

    def record_group_deactivated(self, chat_key: str, title: str) -> None:
        self._write("GROUP-INACTIVE %s «%s»", chat_key, title)

    def record_group_restored(self, chat_key: str, title: str) -> None:
        self._write("GROUP-RESTORED %s «%s»", chat_key, title)

    def record_group_renamed(self, chat_key: str, title: str) -> None:
        self._write("GROUP-RENAMED %s «%s»", chat_key, title)

    def record_group_deleted_by_admin(self, chat_key: str, project: str) -> None:
        self._write("GROUP-DELETED %s «%s» (manual)", chat_key, project)

    def _record_request(self, outcome: str, person: Person, project: str) -> None:
        self._write("%s id=%s @%s project=%s", outcome, person.user_id, person.username, project)

    def _record_by_id(self, outcome: str, user_id: int, project: str) -> None:
        self._write("%s id=%s project=%s", outcome, user_id, project)

    def _write(self, message: str, *args: object) -> None:
        self._file_logger.info(message, *args)
        logger.info(message, *args)
