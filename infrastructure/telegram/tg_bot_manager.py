import structlog
from aiogram import Bot

from app.config import BotConfig

logger = structlog.get_logger(__name__)


class TelegramBotManager:
    """Manages multiple Telegram bot instances mapped by connector IDs.

    This class is responsible for creating, storing, and managing `Bot` objects
    based on provided configuration data. It allows easy retrieval of a bot by
    its connector ID and provides lifecycle management for all bot sessions.
    """

    def __init__(self, bots_config: list[BotConfig]):
        """Initializes the manager with a list of bot configurations."""
        self._bots: dict[str, Bot] = {}
        for cfg in bots_config:
            self._bots[cfg.connector_id] = Bot(cfg.bot_token)

    def get_bot_by_connector_id(self, connector_id: str) -> Bot:
        """Retrieves a bot instance by its connector ID."""
        bot = self._bots.get(connector_id)
        if bot is None:
            raise KeyError(f"Invalid connector_id: {connector_id}")
        return bot

    async def close_sessions(self) -> None:
        """Closes all active aiohttp sessions for managed bots."""
        for bot in self._bots.values():
            await bot.session.close()
        logger.debug("Bot sessions closed")

    @property
    def bots(self) -> dict[str, Bot]:
        """Returns a mapping of connector IDs to their corresponding bot instances."""
        return self._bots
