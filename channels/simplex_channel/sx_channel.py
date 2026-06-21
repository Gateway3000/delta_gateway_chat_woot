from typing import Any

from channels.simplex_channel.sx_bot_manager import SimplexBotManager
from channels.simplex_channel.sx_message_processor import SimplexMessageProcessor
from channels.simplex_channel.sx_receiver import SimplexReceiver
from channels.simplex_channel.sx_routing import SimplexRouting
from channels.simplex_channel.sx_transport import SimplexTransport
from src import ChannelDeliveryResult, Envelope, IChannel


class SimplexChannel(IChannel):
    channel = "simplex"

    def __init__(
        self,
        bot_manager: SimplexBotManager,
        routing: SimplexRouting,
        transport: SimplexTransport,
        io_processor: SimplexMessageProcessor,
        receiver: SimplexReceiver,
    ) -> None:
        self._bot_manager = bot_manager
        self._routing = routing
        self._transport = transport
        self._io_processor = io_processor
        self._receiver = receiver

    async def on_startup(self) -> None:
        # SimpleX has no inbound webhook; open the persistent CLI WebSocket
        # connections (which also set up the bot address + auto-accept), then
        # start draining inbound messages from them.
        await self._bot_manager.start_all()
        await self._receiver.start()

    async def on_shutdown(self) -> None:
        await self._receiver.stop()
        await self._bot_manager.close_sessions()

    def get_route_by_connector_id(self, connector_id: str) -> dict[str, str]:
        return self._routing.get_route_by_connector_id(connector_id)

    async def send_to_user(
        self, message: dict[str, Any], limiter: Any = None
    ) -> ChannelDeliveryResult:
        return await self._transport.send_to_simplex_user(message)

    async def build_channel_message(
        self, raw_data: dict[str, Any]
    ) -> tuple[str, Envelope]:
        return await self._io_processor.build_channel_message(raw_data)

    async def publish_channel_message(
        self,
        idempotency_key: str,
        envelope: Envelope,
        raw_data: dict[str, Any],
    ) -> None:
        await self._io_processor.publish_channel_message(
            idempotency_key, envelope, raw_data
        )

    async def publish_chatwoot_message(
        self, raw_data: dict[str, Any], cw_account_id: str
    ) -> None:
        await self._io_processor.publish_chatwoot_message(
            raw_data,
            cw_account_id,
            self.channel,
        )
