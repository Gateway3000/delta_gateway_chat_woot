from typing import Any

from channels.signal_channel.sig_bot_manager import SignalBotManager
from channels.signal_channel.sig_message_processor import SignalMessageProcessor
from channels.signal_channel.sig_receiver import SignalReceiver
from channels.signal_channel.sig_routing import SignalRouting
from channels.signal_channel.sig_transport import SignalTransport
from src import ChannelDeliveryResult, Envelope, IChannel


class SignalChannel(IChannel):
    channel = "signal"

    def __init__(
        self,
        bot_manager: SignalBotManager,
        routing: SignalRouting,
        transport: SignalTransport,
        io_processor: SignalMessageProcessor,
        receiver: SignalReceiver,
    ) -> None:
        self._bot_manager = bot_manager
        self._routing = routing
        self._transport = transport
        self._io_processor = io_processor
        self._receiver = receiver

    async def on_startup(self) -> None:
        # Signal has no inbound webhook; start the long-poll receive loop.
        await self._receiver.start()

    async def on_shutdown(self) -> None:
        await self._receiver.stop()
        await self._bot_manager.close_sessions()

    def get_route_by_connector_id(self, connector_id: str) -> dict[str, str]:
        return self._routing.get_route_by_connector_id(connector_id)

    async def send_to_user(
        self, message: dict[str, Any], limiter: Any = None
    ) -> ChannelDeliveryResult:
        return await self._transport.send_to_signal_user(message)

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
