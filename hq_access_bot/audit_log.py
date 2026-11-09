"""Access audit: a separate rotating file, independent of the console log."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from hq_access_bot.whitelist.models import Person

_MAX_FILE_BYTES = 1_000_000
_ROTATED_FILES_KEPT = 3


class AuditLog:
    def __init__(self, path: Path) -> None:
        # A standalone instance outside the registry keeps records out of the console log.
        self._logger = logging.Logger("access", logging.INFO)
        self._handler = RotatingFileHandler(
            path, maxBytes=_MAX_FILE_BYTES, backupCount=_ROTATED_FILES_KEPT, encoding="utf-8"
        )
        self._handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        self._logger.addHandler(self._handler)

    def close(self) -> None:
        self._handler.close()

    def record_request_approved(self, person: Person, project: str) -> None:
        self._record_request("APPROVED", person, project)

    def record_request_declined(self, person: Person, project: str) -> None:
        self._record_request("DECLINED", person, project)

    def record_member_left(self, person: Person, project: str, removed: list[str]) -> None:
        self._logger.info(
            "MEMBER-LEFT id=%s project=%s %s", person.user_id, project, ", ".join(removed)
        )

    def record_members_added(self, project: str, added: list[str]) -> None:
        self._logger.info("ADD project=%s %s", project, ", ".join(added))

    def record_members_removed(self, project: str, removed: list[str]) -> None:
        self._logger.info("REMOVE project=%s %s", project, ", ".join(removed))

    def record_group_registered(self, chat_key: str, title: str) -> None:
        self._logger.info("GROUP-ADDED %s «%s»", chat_key, title)

    def record_group_lost(self, chat_key: str, title: str) -> None:
        self._logger.info("GROUP-REMOVED %s «%s»", chat_key, title)

    def record_group_deleted_by_admin(self, chat_key: str, project: str) -> None:
        self._logger.info("GROUP-DELETED %s «%s» (manual)", chat_key, project)

    def _record_request(self, outcome: str, person: Person, project: str) -> None:
        self._logger.info(
            "%s id=%s @%s project=%s", outcome, person.user_id, person.username, project
        )
