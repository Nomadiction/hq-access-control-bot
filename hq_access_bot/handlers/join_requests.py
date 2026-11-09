"""Decisions on requests to join a group."""

from aiogram import Router
from aiogram.types import ChatJoinRequest

from hq_access_bot import texts
from hq_access_bot.handlers.telegram_mapping import build_chat_key, build_person
from hq_access_bot.services import Services
from hq_access_bot.whitelist.identity import Person
from hq_access_bot.whitelist.models import Group


def build_router() -> Router:
    router = Router(name=__name__)
    router.chat_join_request.register(handle_join_request)
    return router


async def handle_join_request(event: ChatJoinRequest, services: Services) -> None:
    """Approve a request from a listed member. A group outside the list declines everyone."""
    person = build_person(event.from_user)
    group = services.whitelist_store.read().groups.get(build_chat_key(event.chat))

    if group is not None and group.has_member(person):
        await _approve(event, person, group, services)
    else:
        project = group.project if group else texts.UNKNOWN_PROJECT
        await _decline(event, person, project, services)


async def _approve(
    event: ChatJoinRequest, person: Person, group: Group, services: Services
) -> None:
    project = group.project
    await event.approve()
    services.audit_log.record_request_approved(person, project)
    if group.needs_confirmation(person):
        async with services.whitelist_store.transaction() as whitelist:
            whitelist.confirm_member(build_chat_key(event.chat), person)
    await services.notifier.send_direct_message(
        person.user_id, texts.format_approved_direct_message(project)
    )
    await services.notifier.notify_admins(texts.format_request_approved_notice(project, person))


async def _decline(
    event: ChatJoinRequest, person: Person, project: str, services: Services
) -> None:
    await event.decline()
    services.audit_log.record_request_declined(person, project)
    await services.notifier.send_direct_message(person.user_id, texts.DECLINED_DIRECT_MESSAGE)
    await services.notifier.notify_admins(texts.format_request_declined_notice(project, person))
