import asyncio
from typing import Any

import httpx

from channels.signal_channel.sig_bot_manager import SignalAPIError, SignalBotManager
from src import ChannelDeliveryResult, Envelope
from src.multichannel_gateway.core.exceptions import (
    FatalError,
    RateLimitError,
    TransientError,
)


class SignalTransport:
    """Handles sending messages to Signal users via signal-cli-rest-api."""

    def __init__(self, bot_manager: SignalBotManager):
        self._bots = bot_manager

    async def send_to_signal_user(
        self, message: dict[str, Any], limiter: Any = asyncio.sleep
    ) -> ChannelDeliveryResult:
        envelope = Envelope.model_validate(message)
        client = self._bots.get_client_by_connector_id(envelope.connector_id)

        recipient = str(envelope.sender.external_id)
        text = str(envelope.payload.get("text") or "").strip()

        if not text:
            raise FatalError("Signal delivery failure: empty text message")

        try:
            await limiter(0.3)
            result = await client.send_text(recipient, text)
            # /v2/send echoes the message timestamp; use it as the external id.
            external_id = str(result.get("timestamp") or "")
            return ChannelDeliveryResult(ok=True, external_id=external_id)

        except (
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.RemoteProtocolError,
        ) as exc:
            # The signal-cli-rest-api container is typically self-hosted and
            # reachable over an internal network, so connectivity blips are
            # expected — treat them as retryable rather than fatal.
            raise TransientError(
                f"Signal transient delivery failure: {repr(exc)}"
            ) from exc
        except SignalAPIError as exc:
            if exc.status == 429:
                raise RateLimitError(
                    f"Signal rate limited: {repr(exc)}",
                    retry_after_seconds=RateLimitError.DEFAULT_RETRY_AFTER_SECONDS,
                ) from exc
            raise FatalError(f"Signal delivery failure: {repr(exc)}") from exc
        except Exception as exc:
            raise FatalError(f"Signal delivery failure: {repr(exc)}") from exc
