"""Entry point: python -m hq_access_bot."""

from hq_access_bot.app import run
from hq_access_bot.config import ConfigurationError
from hq_access_bot.instance_lock import InstanceAlreadyRunningError
from hq_access_bot.whitelist.store import WhitelistCorruptedError

try:
    run()
except (ConfigurationError, InstanceAlreadyRunningError, WhitelistCorruptedError) as error:
    raise SystemExit(str(error)) from error
