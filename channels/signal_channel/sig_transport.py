import asyncio
from typing import Any

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
        if not text:
            raise FatalError("Signal delivery failure: empty text message")

        try:
            await limiter(0.3)
            result = await conn.send(recipient, text)
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
