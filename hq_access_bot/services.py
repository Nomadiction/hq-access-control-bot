"""Collaborators bundled so handlers and their helpers take a single argument."""

from dataclasses import dataclass

from hq_access_bot.audit_log import AuditLog
from hq_access_bot.history_cleaner import HistoryCleaner
from hq_access_bot.notifier import Notifier
from hq_access_bot.whitelist.store import WhitelistStore


@dataclass(frozen=True, slots=True)
class Services:
    whitelist_store: WhitelistStore
    audit_log: AuditLog
    notifier: Notifier
    history_cleaner: HistoryCleaner
