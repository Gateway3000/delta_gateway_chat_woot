import structlog
from aiohttp import ClientSession, ClientTimeout

from channels.session_channel.plugin_settings import BotConfig

logger = structlog.get_logger(__name__)


class SessionBotManager:
    """Manages outbound webhook targets mapped by connector IDs.

    A "bot" here is just a destination URL (the Session TS bridge server).
    This class owns the single shared `aiohttp` session used to deliver
    replies to those URLs and provides lifecycle management for it.
    """

    def __init__(self, bots_config: list[BotConfig], request_timeout_seconds: float = 10.0):
        """Initializes the manager with a list of bot configurations."""
        self._webhook_urls: dict[str, str] = {}
        for cfg in bots_config:
            self._webhook_urls[cfg.connector_id] = cfg.webhook_url
        self._request_timeout_seconds = request_timeout_seconds
        # Created lazily on first access: aiohttp.ClientSession binds to the
        # running event loop, but this manager is constructed synchronously
        # at module-import time by the wiring module (no loop running yet).
        self._session: ClientSession | None = None

    def get_webhook_url_by_connector_id(self, connector_id: str) -> str:
        """Retrieves the outbound webhook URL by its connector ID."""
        url = self._webhook_urls.get(connector_id)
        if url is None:
            raise KeyError(f"Invalid connector_id: {connector_id}")
        return url

    async def close_sessions(self) -> None:
        """Closes the shared aiohttp session, if one was ever opened."""
        if self._session is not None:
            await self._session.close()
        logger.debug("Session channel sessions closed")

    @property
    def session(self) -> ClientSession:
        """Returns the shared aiohttp session used for outbound delivery,
        creating it on first access."""
        if self._session is None:
            self._session = ClientSession(
                timeout=ClientTimeout(total=self._request_timeout_seconds)
            )
        return self._session

    @property
    def webhook_urls(self) -> dict[str, str]:
        """Returns a mapping of connector IDs to their outbound webhook URLs."""
        return self._webhook_urls
