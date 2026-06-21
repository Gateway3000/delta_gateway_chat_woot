from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp
import structlog

from channels.whatsapp_channel.plugin_settings import WhatsAppSettings
from channels.whatsapp_channel.wa_routing import WhatsAppRouting
from src import ChannelDeliveryResult, Envelope
from src.multichannel_gateway.core.exceptions import (
    FatalError,
    RateLimitError,
    TransientError,
)

logger = structlog.get_logger(__name__)


class WhatsAppTransport:
    """Sends Chatwoot -> WhatsApp messages by calling the sidecar /send API."""

    def __init__(self, routing: WhatsAppRouting, settings: WhatsAppSettings) -> None:
        self._routing = routing
        self._settings = settings

    def _internal_url(self, data_url: str | None) -> str | None:
        """Rewrite a Chatwoot attachment URL to the internally-reachable host.

        Chatwoot builds attachment URLs from its public/FRONTEND_URL (often
        localhost), which the sidecar can't fetch from inside Docker. Swap the
        scheme+host for CHATWOOT_BASE_URL (e.g. http://chatwoot-web:3000) so the
        sidecar pulls the real bytes instead of a 404 page.
        """
        if not data_url:
            return data_url
        base = self._settings.chatwoot_base_url
        if not base:
            return data_url
        b = urlsplit(base)
        p = urlsplit(data_url)
        return urlunsplit((b.scheme, b.netloc, p.path, p.query, p.fragment))

    async def send_to_whatsapp_user(
        self, message: dict[str, Any]
    ) -> ChannelDeliveryResult:
        envelope = Envelope.model_validate(message)
        route = self._routing.get_route_by_connector_id(envelope.connector_id)
        url = route["sidecar_url"].rstrip("/") + "/send"

        # envelope.sender.external_id is the JID (channel prefix already stripped
        # by the Chatwoot webhook handler).
        body = {
            "to": envelope.sender.external_id,
            "text": str(envelope.payload.get("text") or ""),
            "attachments": [
                {
                    "data_url": self._internal_url(a.get("data_url")),
                    "mime_type": a.get("mime_type") or a.get("content_type"),
                    "filename": a.get("filename"),
                }
                for a in envelope.payload.get("attachments", [])
                if a.get("data_url")
            ],
        }

        headers = {}
        if self._settings.sidecar_token:
            headers["Authorization"] = f"Bearer {self._settings.sidecar_token}"

        timeout = aiohttp.ClientTimeout(total=self._settings.send_timeout_seconds)
        try:
            async with aiohttp.ClientSession(
                timeout=timeout, headers=headers
            ) as session:
                async with session.post(url, json=body) as resp:
                    text = await resp.text()
                    if resp.status == 503:
                        # sidecar not connected yet — retry later
                        raise TransientError(f"WhatsApp sidecar not connected: {text}")
                    if resp.status == 429:
                        raise RateLimitError("WhatsApp sidecar rate limited")
                    if 500 <= resp.status < 600:
                        raise TransientError(f"sidecar {resp.status}: {text}")
                    if resp.status >= 400:
                        raise FatalError(f"sidecar {resp.status}: {text}")
                    data = await resp.json()
        except (aiohttp.ClientConnectionError, TimeoutError) as exc:
            raise TransientError(f"WhatsApp sidecar unreachable: {exc!r}") from exc

        ids = data.get("ids") or []
        return ChannelDeliveryResult(
            ok=True, external_id=",".join(str(i) for i in ids if i)
        )
