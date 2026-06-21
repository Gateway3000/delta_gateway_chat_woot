import asyncio
from typing import Any

from channels.simplex_channel.sx_bot_manager import SimplexBotManager, SimplexError
from src import ChannelDeliveryResult, Envelope
from src.multichannel_gateway.core.exceptions import FatalError, TransientError


class SimplexTransport:
    """Sends messages to SimpleX users via the simplex-chat CLI."""

    def __init__(self, bot_manager: SimplexBotManager):
        self._bots = bot_manager

    async def send_to_simplex_user(
        self, message: dict[str, Any], limiter: Any = asyncio.sleep
    ) -> ChannelDeliveryResult:
        envelope = Envelope.model_validate(message)
        conn = self._bots.get_client_by_connector_id(envelope.connector_id)

        contact_id = str(envelope.sender.external_id)
        text = str(envelope.payload.get("text") or "").strip()
        if not text:
            raise FatalError("SimpleX delivery failure: empty text message")

        try:
            await limiter(0.3)
            result = await conn.send_text(contact_id, text)
        except SimplexError as exc:
            if exc.transient:
                raise TransientError(
                    f"SimpleX transient delivery failure: {exc}"
                ) from exc
            raise FatalError(f"SimpleX delivery failure: {exc}") from exc

        # A successful APISendMessages reply carries the sent chat item(s).
        external_id = ""
        items = result.get("chatItems") if isinstance(result, dict) else None
        if items:
            meta = (items[0].get("chatItem") or {}).get("meta") or {}
            external_id = str(meta.get("itemId") or "")

        return ChannelDeliveryResult(ok=True, external_id=external_id)
