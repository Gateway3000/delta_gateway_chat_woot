from typing import Any

from aiohttp import ClientConnectorError, ClientResponseError, ServerDisconnectedError

from channels.session_channel.session_bot_manager import SessionBotManager
from channels.session_channel.plugin_settings import BOT_SOURCE
from src import ChannelDeliveryResult, Envelope
from src.multichannel_gateway.core.exceptions import FatalError, TransientError


class SessionTransport:
    """Handles sending replies to session users via webhook POST to the TS bridge."""

    def __init__(self, bot_manager: SessionBotManager, bot_source_name: str = BOT_SOURCE):
        self._bots = bot_manager
        self._bot_source_name = bot_source_name

    async def send_to_session_user(
        self, message: dict[str, Any], limiter: Any = None
    ) -> ChannelDeliveryResult:
        envelope = Envelope.model_validate(message)
        connector_id = envelope.connector_id
        webhook_url = self._bots.get_webhook_url_by_connector_id(connector_id)
        text = str(envelope.payload.get("text") or "").strip()

        if not text:
            raise FatalError("Session delivery failure: no text to send")

        # NOTE: deliberately do NOT set "source" here. The bridge's /webhook
        # send endpoint ignores any payload whose source == its ignoreSource
        # (also "session_bot"), treating it as its own looped-back inbound
        # traffic and returning 202 without sending. Sending the marker on the
        # reply path silently drops every outbound message.
        outbound_payload = {
            "to": envelope.sender.external_id,
            "text": text,
        }

        try:
            async with self._bots.session.post(
                webhook_url, json=outbound_payload
            ) as resp:
                resp.raise_for_status()
            return ChannelDeliveryResult(ok=True, external_id=envelope.message_id)
        except (
            ClientConnectorError,
            TimeoutError,
            ServerDisconnectedError,
        ) as exc:
            raise TransientError(
                f"Session transient delivery failure: {repr(exc)}"
            ) from exc
        except ClientResponseError as exc:
            raise FatalError(f"Session delivery failure: {repr(exc)}") from exc
        except Exception as exc:
            raise FatalError(f"Session delivery failure: {repr(exc)}") from exc
