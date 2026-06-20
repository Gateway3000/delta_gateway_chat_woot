from __future__ import annotations

import structlog
import httpx

from channels.imessage_channel.plugin_settings import BotConfig

logger = structlog.get_logger(__name__)


class BlueBubblesClient:
    """Thin async REST client for a single BlueBubbles server.

    There is no official SDK (unlike aiogram for Telegram), so this wraps
    httpx directly. Auth is a `password` query param on every request
    (BlueBubbles also accepts `guid` / `token` as aliases — we standardize
    on `password`).
    """

    def __init__(self, server_url: str, server_password: str, send_method: str):
        self.server_url = server_url.rstrip("/")
        self.send_method = send_method
        self._password = server_password
        self._client = httpx.AsyncClient(timeout=15.0)

    async def _request(
        self, method: str, path: str, *, json: dict | None = None
    ) -> dict:
        url = f"{self.server_url}{path}"
        resp = await self._client.request(
            method, url, params={"password": self._password}, json=json
        )
        body = resp.json()
        # BlueBubbles wraps every response as {status, message, data}.
        # A non-2xx `status` in the body is the platform's real error
        # signal — the HTTP status code alone isn't always reliable.
        if resp.status_code >= 400 or body.get("status", 200) >= 400:
            raise BlueBubblesAPIError(
                status=body.get("status", resp.status_code),
                message=body.get("message", resp.text[:200]),
            )
        return body

    async def send_text(self, chat_guid: str, text: str, temp_guid: str) -> dict:
        return await self._request(
            "POST",
            "/api/v1/message/text",
            json={
                "chatGuid": chat_guid,
                "tempGuid": temp_guid,
                "message": text,
                "method": self.send_method,
            },
        )

    async def send_attachment(
        self, chat_guid: str, file_bytes: bytes, filename: str, mime_type: str
    ) -> dict:
        url = f"{self.server_url}/api/v1/message/attachment"
        resp = await self._client.post(
            url,
            params={"password": self._password},
            data={"chatGuid": chat_guid, "method": self.send_method},
            files={"attachment": (filename, file_bytes, mime_type)},
        )
        body = resp.json()
        if resp.status_code >= 400 or body.get("status", 200) >= 400:
            raise BlueBubblesAPIError(
                status=body.get("status", resp.status_code),
                message=body.get("message", resp.text[:200]),
            )
        return body

    async def download_attachment(self, attachment_guid: str) -> bytes:
        url = f"{self.server_url}/api/v1/attachment/{attachment_guid}/download"
        resp = await self._client.get(url, params={"password": self._password})
        if resp.status_code >= 400:
            raise BlueBubblesAPIError(
                status=resp.status_code,
                message=f"attachment download failed: {resp.text[:200]}",
            )
        return resp.content

    async def close(self) -> None:
        await self._client.aclose()


class BlueBubblesAPIError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"BlueBubbles API error [{status}]: {message}")


class IMessageBotManager:
    """Manages multiple BlueBubbles server connections mapped by connector IDs.

    Mirrors TelegramBotManager's role, but each "bot" here is a connection
    to a distinct, self-hosted BlueBubbles server rather than a token issued
    by a central platform.
    """

    def __init__(self, bots_config: list[BotConfig]):
        self._clients: dict[str, BlueBubblesClient] = {}
        for cfg in bots_config:
            self._clients[cfg.connector_id] = BlueBubblesClient(
                cfg.server_url, cfg.server_password, cfg.send_method
            )

    def get_client_by_connector_id(self, connector_id: str) -> BlueBubblesClient:
        client = self._clients.get(connector_id)
        if client is None:
            raise KeyError(f"Invalid connector_id: {connector_id}")
        return client

    async def close_sessions(self) -> None:
        for client in self._clients.values():
            await client.close()
        logger.debug("BlueBubbles client sessions closed")

    @property
    def clients(self) -> dict[str, BlueBubblesClient]:
        return self._clients
