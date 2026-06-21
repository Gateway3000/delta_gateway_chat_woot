import asyncio
import base64
from typing import Any

import httpx

from channels.signal_channel.sig_bot_manager import SignalBotManager, SignalBridgeError
from src import ChannelDeliveryResult, Envelope
from src.multichannel_gateway.core.exceptions import FatalError, TransientError


class SignalTransport:
    """Sends messages to Signal users via the signal-bridge daemon."""

    def __init__(self, bot_manager: SignalBotManager):
        self._bots = bot_manager

    async def send_to_signal_user(
        self, message: dict[str, Any], limiter: Any = asyncio.sleep
    ) -> ChannelDeliveryResult:
        envelope = Envelope.model_validate(message)
        conn = self._bots.get_client_by_connector_id(envelope.connector_id)

        recipient = str(envelope.sender.external_id)
        text = str(envelope.payload.get("text") or "").strip()
        attachments = await self._prepare_attachments(
            list(envelope.payload.get("attachments") or [])
        )
        if not text and not attachments:
            raise FatalError("Signal delivery failure: empty message")

        try:
            await limiter(0.3)
            result = await conn.send(recipient, text, attachments)
        except SignalBridgeError as exc:
            # Connection drops / timeouts are recoverable; let the queue retry.
            if exc.transient:
                raise TransientError(
                    f"Signal transient delivery failure: {exc}"
                ) from exc
            raise FatalError(f"Signal delivery failure: {exc}") from exc

        if not result.get("ok"):
            # The bridge reached Signal but the send itself failed — not retryable.
            raise FatalError(
                f"Signal delivery failure: {result.get('error') or 'unknown error'}"
            )

        return ChannelDeliveryResult(
            ok=True, external_id=str(result.get("timestamp") or "")
        )

    @staticmethod
    async def _prepare_attachments(
        attachments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Download each Chatwoot attachment and base64-encode it for the bridge.

        The bridge accepts attachment bytes inline as base64 (so each send stays
        a single JSON line), so we fetch the file from its Chatwoot `data_url`
        here and hand the bridge `{data, content_type, filename}`.
        """
        prepared: list[dict[str, Any]] = []
        for attachment in attachments:
            data_url = attachment.get("data_url") or attachment.get("url")
            if not data_url:
                continue
            file_bytes = await SignalTransport._fetch_outbound_attachment(str(data_url))
            prepared.append(
                {
                    "data": base64.b64encode(file_bytes).decode("ascii"),
                    "content_type": attachment.get("mime_type")
                    or attachment.get("content_type"),
                    "filename": attachment.get("filename")
                    or attachment.get("file_name"),
                }
            )
        return prepared

    @staticmethod
    async def _fetch_outbound_attachment(data_url: str) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(data_url)
                resp.raise_for_status()
                return resp.content
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            # The file lives in Chatwoot; a network blip there is retryable.
            raise TransientError(
                f"Signal attachment download failed: {exc!r}"
            ) from exc
        except httpx.HTTPError as exc:
            raise FatalError(
                f"Signal attachment download failed: {exc!r}"
            ) from exc
