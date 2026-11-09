"""Decisions on requests to join a group."""

import logging

from aiogram import Router
from aiogram.types import ChatJoinRequest

from hq_access_bot import texts
from hq_access_bot.handlers.telegram_mapping import build_person
from hq_access_bot.services import Services
from hq_access_bot.whitelist.models import Member, Person

logger = logging.getLogger(__name__)


def build_router() -> Router:
    router = Router(name=__name__)
    router.chat_join_request.register(handle_join_request)
    return router


async def handle_join_request(event: ChatJoinRequest, services: Services) -> None:
    """Approve a request from a listed member. A group outside the list declines everyone."""
    person = build_person(event.from_user)
    group = services.whitelist_store.read().groups.get(str(event.chat.id))
    project = group.project if group else texts.UNKNOWN_PROJECT
    member = group.find_member(person) if group else None

    if member is None:
        await _decline(event, person, project, services)
    else:
        await _approve(event, person, member, project, services)


async def _approve(
    event: ChatJoinRequest, person: Person, member: Member, project: str, services: Services
) -> None:
    await event.approve()
    logger.info(
        "APPROVED id=%s @%s -> %s (%s)", person.user_id, person.username, event.chat.id, project
    )
    services.audit_log.record_request_approved(person, project)
    if member.is_outdated_for(person):
        async with services.whitelist_store.transaction() as whitelist:
            whitelist.confirm_member(str(event.chat.id), person)
    await services.notifier.send_direct_message(
        person.user_id, texts.format_approved_direct_message(project)
    )
    await services.notifier.notify_admins(texts.format_request_approved_notice(project, person))


async def _decline(
    event: ChatJoinRequest, person: Person, project: str, services: Services
) -> None:
    await event.decline()
    logger.info("DECLINED id=%s @%s -> %s", person.user_id, person.username, event.chat.id)
    services.audit_log.record_request_declined(person, project)
    await services.notifier.send_direct_message(person.user_id, texts.DECLINED_DIRECT_MESSAGE)
    await services.notifier.notify_admins(texts.format_request_declined_notice(project, person))
