import asyncio
import uuid
from typing import Any

import httpx

from channels.imessage_channel.im_bot_manager import (
    BlueBubblesAPIError,
    IMessageBotManager,
)
from src import ChannelDeliveryResult, Envelope
from src.multichannel_gateway.core.exceptions import (
    RateLimitError,
    FatalError,
    TransientError,
)


class IMessageTransport:
    """Handles sending messages to iMessage users via BlueBubbles."""

    def __init__(self, bot_manager: IMessageBotManager):
        self._bots = bot_manager

    async def send_to_imessage_user(
        self, message: dict[str, Any], limiter: Any = asyncio.sleep
    ) -> ChannelDeliveryResult:
        envelope = Envelope.model_validate(message)
        connector_id = envelope.connector_id
        client = self._bots.get_client_by_connector_id(connector_id)

        chat_guid = str(envelope.payload.get("chat_guid") or envelope.sender.external_id)
        text = str(envelope.payload.get("text") or "").strip()
        attachments = envelope.payload.get("attachments", [])
        sent_message_ids: list[str] = []

        try:
            await limiter(0.3)

            if text:
                result = await client.send_text(
                    chat_guid, text, temp_guid=f"gw-{uuid.uuid4().hex[:12]}"
                )
                sent_message_ids.append(str(result["data"]["guid"]))

            for attachment in attachments:
                data_url = attachment.get("data_url")
                if not data_url:
                    continue
                file_bytes = await self._fetch_outbound_attachment(data_url)
                result = await client.send_attachment(
                    chat_guid,
                    file_bytes,
                    filename=attachment.get("filename", "attachment"),
                    mime_type=attachment.get("mime_type", "application/octet-stream"),
                )
                sent_message_ids.append(str(result["data"]["guid"]))

            if not sent_message_ids:
                raise FatalError("BlueBubbles delivery failure: no text or attachments")

            return ChannelDeliveryResult(
                ok=True, external_id=",".join(sent_message_ids)
            )

        except (
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.RemoteProtocolError,
        ) as exc:
            # BlueBubbles servers are self-hosted Macs reachable over a
            # tunnel/LAN rather than a vendor cloud endpoint, so network
            # flakiness here is the norm, not the exception — treat it as
            # transient/retryable rather than fatal.
            raise TransientError(
                f"BlueBubbles transient delivery failure: {repr(exc)}"
            ) from exc
        except BlueBubblesAPIError as exc:
            if exc.status == 429:
                raise RateLimitError(
                    f"BlueBubbles rate limited: {repr(exc)}",
                    retry_after_seconds=RateLimitError.DEFAULT_RETRY_AFTER_SECONDS,
                ) from exc
            raise FatalError(f"BlueBubbles delivery failure: {repr(exc)}") from exc
        except Exception as exc:
            raise FatalError(f"BlueBubbles delivery failure: {repr(exc)}") from exc

    @staticmethod
    async def _fetch_outbound_attachment(data_url: str) -> bytes:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(data_url)
            resp.raise_for_status()
            return resp.content
