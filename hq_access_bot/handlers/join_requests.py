"""Decisions on requests to join a group."""

import logging
from collections.abc import Awaitable, Callable

from aiogram import Router
from aiogram.exceptions import AiogramError, TelegramBadRequest
from aiogram.types import ChatJoinRequest

from hq_access_bot import texts
from hq_access_bot.handlers.telegram_mapping import build_chat_key, build_person
from hq_access_bot.services import Services
from hq_access_bot.telegram_retry import call_with_retry
from hq_access_bot.whitelist.identity import Person
from hq_access_bot.whitelist.models import Group
from hq_access_bot.whitelist.store import WhitelistCorruptedError

logger = logging.getLogger(__name__)

# Telegram's error codes for a request that an admin or an earlier attempt already resolved.
_ALREADY_RESOLVED_ERRORS = ("HIDE_REQUESTER_MISSING", "USER_ALREADY_PARTICIPANT")


def build_router() -> Router:
    router = Router(name=__name__)
    router.chat_join_request.register(handle_join_request)
    return router


async def handle_join_request(event: ChatJoinRequest, services: Services) -> None:
    """Approve a request from a listed member. A group outside the list declines everyone.

    The person is told first: Telegram allows a message to someone who never started the
    bot only through user_chat_id, for 5 minutes and while the request is still open.
    """
    person = build_person(event.from_user)
    try:
        group = services.whitelist_store.read().groups.get(build_chat_key(event.chat))
    except WhitelistCorruptedError:
        await _report_undecided_request(event, person, texts.UNKNOWN_PROJECT, services)
        raise

    if group is not None and group.has_member(person):
        await _approve(event, person, group, services)
    else:
        project = group.project if group else texts.UNKNOWN_PROJECT
        await _decline(event, person, project, services)


async def _approve(
    event: ChatJoinRequest, person: Person, group: Group, services: Services
) -> None:
    project = group.project
    await services.notifier.send_direct_message(
        event.user_chat_id, texts.format_approved_direct_message(project)
    )
    if not await _apply_decision(event.approve, event, person, project, services):
        return
    services.audit_log.record_request_approved(person, project)
    if group.needs_confirmation(person):
        async with services.whitelist_store.transaction() as whitelist:
            whitelist.confirm_member(build_chat_key(event.chat), person)
    await services.notifier.notify_admins(texts.format_request_approved_notice(project, person))


async def _decline(
    event: ChatJoinRequest, person: Person, project: str, services: Services
) -> None:
    await services.notifier.send_direct_message(event.user_chat_id, texts.DECLINED_DIRECT_MESSAGE)
    if not await _apply_decision(event.decline, event, person, project, services):
        return
    services.audit_log.record_request_declined(person, project)
    await services.notifier.notify_admins(texts.format_request_declined_notice(project, person))


async def _apply_decision(
    decide: Callable[[], Awaitable[object]],
    event: ChatJoinRequest,
    person: Person,
    project: str,
    services: Services,
) -> bool:
    """Return whether Telegram accepted the decision.

    A lost decision cannot be recovered later, because the Bot API has no way to list
    open requests, so a failure is handed over to the admins. A request that is already
    resolved needs nobody's attention.
    """
    try:
        await call_with_retry(decide)
    except AiogramError as error:
        logger.warning("Decision on request of user %s failed: %s", person.user_id, error)
        if not _is_already_resolved(error):
            await _report_undecided_request(event, person, project, services)
        return False
    return True


def _is_already_resolved(error: AiogramError) -> bool:
    return isinstance(error, TelegramBadRequest) and any(
        code in error.message.upper() for code in _ALREADY_RESOLVED_ERRORS
    )


async def _report_undecided_request(
    event: ChatJoinRequest, person: Person, project: str, services: Services
) -> None:
    services.audit_log.record_request_failed(person, project)
    await services.notifier.send_direct_message(
        event.user_chat_id, texts.REQUEST_FAILED_DIRECT_MESSAGE
    )
    await services.notifier.notify_admins(texts.format_request_failed_notice(project, person))
