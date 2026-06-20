from __future__ import annotations

from typing import Any

import httpx
import structlog

from channels.signal_channel.plugin_settings import BotConfig

logger = structlog.get_logger(__name__)


class SignalAPIError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"Signal API error [{status}]: {message}")


class SignalClient:
    """Thin async REST client for one Signal account in signal-cli-rest-api.

    There is no official SDK, so this wraps httpx directly (like the
    BlueBubbles client). Each client is bound to a single registered
    `number`; `api_url` is the container base URL.

    Unlike Telegram/iMessage, the container never calls us back — inbound
    messages are pulled via `receive()` (`GET /v1/receive/{number}`), which
    long-polls and returns a JSON array of envelopes, consuming them from
    signal-cli's queue in the process.
    """

    def __init__(self, number: str, api_url: str, receive_timeout: int):
        self.number = number
        self.api_url = api_url.rstrip("/")
        self._receive_timeout = receive_timeout
        self._client = httpx.AsyncClient(timeout=15.0)
        # The receive long-poll can block up to `receive_timeout` seconds
        # server-side, so it needs its own, more generous client timeout.
        self._receive_client = httpx.AsyncClient(timeout=receive_timeout + 15.0)

    async def receive(self) -> list[dict[str, Any]]:
        """Long-poll for new messages, returning the raw envelope list."""
        url = f"{self.api_url}/v1/receive/{self.number}"
        resp = await self._receive_client.get(
            url, params={"timeout": self._receive_timeout}
        )
        if resp.status_code >= 400:
            raise SignalAPIError(status=resp.status_code, message=resp.text[:200])
        data = resp.json()
        # Normal mode returns a JSON array of envelopes.
        return data if isinstance(data, list) else []

    async def send_text(self, recipient: str, message: str) -> dict[str, Any]:
        url = f"{self.api_url}/v2/send"
        resp = await self._client.post(
            url,
            json={
                "number": self.number,
                "recipients": [recipient],
                "message": message,
            },
        )
        body: dict[str, Any] = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            raise SignalAPIError(
                status=resp.status_code,
                message=str(body.get("error", resp.text[:200])),
            )
        return body

    async def close(self) -> None:
        await self._client.aclose()
        await self._receive_client.aclose()


class SignalBotManager:
    """Manages one SignalClient per connector_id.

    Mirrors IMessageBotManager — each "bot" is a distinct Signal account
    (number) inside a signal-cli-rest-api container.
    """

    def __init__(self, bots_config: list[BotConfig], receive_timeout: int):
        self._clients: dict[str, SignalClient] = {}
        for cfg in bots_config:
            self._clients[cfg.connector_id] = SignalClient(
                cfg.number, cfg.api_url, receive_timeout
            )

    def get_client_by_connector_id(self, connector_id: str) -> SignalClient:
        client = self._clients.get(connector_id)
        if client is None:
            raise KeyError(f"Invalid connector_id: {connector_id}")
        return client

    async def close_sessions(self) -> None:
        for client in self._clients.values():
            await client.close()
        logger.debug("Signal client sessions closed")

    @property
    def clients(self) -> dict[str, SignalClient]:
        return self._clients
