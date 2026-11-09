"""Base type for failures the bot cannot work around."""


class FatalBotError(Exception):
    """An operator has to fix the cause before the bot can do its job."""
