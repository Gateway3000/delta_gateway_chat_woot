from typing import Any

from channels.whatsapp_channel.wa_message_processor import WhatsAppMessageProcessor
from channels.whatsapp_channel.wa_routing import WhatsAppRouting
from channels.whatsapp_channel.wa_transport import WhatsAppTransport
from src import ChannelDeliveryResult, Envelope, IChannel


class WhatsAppChannel(IChannel):
    channel = "whatsapp"

    def __init__(
        self,
        routing: WhatsAppRouting,
        transport: WhatsAppTransport,
        io_processor: WhatsAppMessageProcessor,
    ) -> None:
        self._routing = routing
        self._transport = transport
        self._io_processor = io_processor

    # Inbound arrives via the gateway's existing /ingest/incoming/whatsapp/...
    # webhook (posted by the sidecar), so there is no webhook to register and no
    # background listener to start here.

    def get_route_by_connector_id(self, connector_id: str) -> dict[str, str]:
        return self._routing.get_route_by_connector_id(connector_id)

    async def send_to_user(
        self, message: dict[str, Any], limiter: Any = None
    ) -> ChannelDeliveryResult:
        return await self._transport.send_to_whatsapp_user(message)

    async def build_channel_message(
        self, raw_data: dict[str, Any]
    ) -> tuple[str, Envelope]:
        return await self._io_processor.build_channel_message(raw_data)

    async def publish_channel_message(
        self, idempotency_key: str, envelope: Envelope, raw_data: dict[str, Any]
    ) -> None:
        await self._io_processor.publish_channel_message(idempotency_key, envelope)

    async def publish_chatwoot_message(
        self, raw_data: dict[str, Any], cw_account_id: str
    ) -> None:
        await self._io_processor.publish_chatwoot_message(
            raw_data, cw_account_id, self.channel
        )
