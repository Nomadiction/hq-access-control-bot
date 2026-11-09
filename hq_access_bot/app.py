"""Application assembly and polling startup."""

import asyncio
import logging
import time
from contextlib import closing

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent

from hq_access_bot.audit_log import AuditLog
from hq_access_bot.bot_profile import setup_bot_profile
from hq_access_bot.config import DATA_DIR, DataPaths, Settings, load_settings
from hq_access_bot.handlers import (
    admin_commands,
    bot_membership,
    chat_membership,
    join_requests,
    public_commands,
)
from hq_access_bot.instance_lock import hold_instance_lock
from hq_access_bot.notifier import Notifier
from hq_access_bot.services import Services
from hq_access_bot.whitelist.models import Whitelist
from hq_access_bot.whitelist.store import WhitelistStore

logger = logging.getLogger(__name__)


def run() -> None:
    """Run the bot, blocking the thread until it stops.

    Raises:
        ConfigurationError: the settings are invalid.
        InstanceAlreadyRunningError: the bot is already running.
        WhitelistCorruptedError: the access list file is unreadable.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data_paths = DataPaths.inside(DATA_DIR)
    with hold_instance_lock(data_paths.instance_lock):
        asyncio.run(serve(settings, data_paths))


def build_dispatcher(settings: Settings, services: Services) -> Dispatcher:
    """Build the dispatcher; dependencies reach handlers by parameter name."""
    dispatcher = Dispatcher(
        settings=settings,
        services=services,
        started_at_seconds=time.time(),
    )
    dispatcher.include_routers(
        join_requests.build_router(),
        chat_membership.build_router(),
        bot_membership.build_router(),
        public_commands.build_router(),
        admin_commands.build_router(),
    )
    dispatcher.errors.register(_log_update_error)
    return dispatcher


async def _prepare_bot(bot: Bot, admin_ids: frozenset[int]) -> None:
    """Prepare the bot for polling.

    Pending updates are kept: otherwise a join request filed while the bot was off
    would hang unanswered forever.
    """
    await bot.delete_webhook(drop_pending_updates=False)
    await setup_bot_profile(bot, admin_ids)


async def serve(settings: Settings, data_paths: DataPaths) -> None:
    """Validate the list file, prepare the bot and run until polling stops."""
    whitelist_store = WhitelistStore(data_paths.whitelist)
    _report_loaded_state(whitelist_store.read(), settings)

    bot_defaults = DefaultBotProperties(parse_mode=ParseMode.HTML)
    with closing(AuditLog(data_paths.audit_log)) as audit_log:
        async with Bot(token=settings.bot_token, default=bot_defaults) as bot:
            notifier = Notifier(bot, settings.admin_ids)
            services = Services(whitelist_store, audit_log, notifier)
            dispatcher = build_dispatcher(settings, services)
            await _prepare_bot(bot, settings.admin_ids)
            logger.info("Bot started. Admins: %s", set(settings.admin_ids) or "none")
            await dispatcher.start_polling(bot)


def _report_loaded_state(whitelist: Whitelist, settings: Settings) -> None:
    logger.info(
        "Loaded groups: %d, members: %d",
        len(whitelist.groups),
        whitelist.count_unique_members(),
    )
    if not settings.admin_ids:
        logger.warning("ADMIN_IDS is empty, admin commands and notifications are unavailable.")


async def _log_update_error(event: ErrorEvent) -> bool:
    logger.error("Failed to process update", exc_info=event.exception)
    return True
