from typing import Any

from channels.session_channel.session_bot_manager import SessionBotManager
from channels.session_channel.session_message_processor import SessionMessageProcessor
from channels.session_channel.session_routing import SessionRouting
from channels.session_channel.session_transport import SessionTransport
from src import ChannelDeliveryResult, Envelope, IChannel


class SessionChannel(IChannel):
    channel = "session"

    def __init__(
        self,
        bot_manager: SessionBotManager,
        routing: SessionRouting,
        transport: SessionTransport,
        io_processor: SessionMessageProcessor,
    ) -> None:
        self._bot_manager = bot_manager
        self._routing = routing
        self._transport = transport
        self._io_processor = io_processor

    async def on_prefork(self) -> None:
        # No webhook registration step: Session's reply target is a static
        # --webhook-url configured per connector, not something we register
        # with a remote API at startup.
        pass

    async def on_shutdown(self) -> None:
        await self._bot_manager.close_sessions()

    def get_route_by_connector_id(self, connector_id: str) -> dict[str, str]:
        return self._routing.get_route_by_connector_id(connector_id)

    async def send_to_user(
        self, message: dict[str, Any], limiter: Any = None
    ) -> ChannelDeliveryResult:
        return await self._transport.send_to_session_user(message)

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
