"""Entry point: python -m hq_access_bot."""

from hq_access_bot.app import run
from hq_access_bot.errors import FatalBotError

try:
    run()
except FatalBotError as error:
    raise SystemExit(str(error)) from error
