from typing import Any

from channels.telegram_channel.tg_bot_manager import TelegramBotManager
from channels.telegram_channel.tg_message_processor import TelegramMessageProcessor
from channels.telegram_channel.tg_routing import TelegramRouting
from channels.telegram_channel.tg_transport import TelegramTransport
from channels.telegram_channel.tg_wh_manager import TelegramWebhookManager
from src import IChannel, ChannelDeliveryResult, Envelope


class TelegramChannel(IChannel):
    channel = "telegram"

    def __init__(
        self,
        bot_manager: TelegramBotManager,
        routing: TelegramRouting,
        transport: TelegramTransport,
        io_processor: TelegramMessageProcessor,
        wh_manager: TelegramWebhookManager,
    ) -> None:
        self._bot_manager = bot_manager
        self._routing = routing
        self._transport = transport
        self._io_processor = io_processor
        self._wh_manager = wh_manager

    async def on_prefork(self) -> None:
        await self._wh_manager.set_wh()

    async def on_shutdown(self) -> None:
        await self._bot_manager.close_sessions()

    def get_route_by_connector_id(self, connector_id: str) -> dict[str, str]:
        return self._routing.get_route_by_connector_id(connector_id)

    async def send_to_user(
        self, message: dict[str, Any], limiter: Any = None
    ) -> ChannelDeliveryResult:
        return await self._transport.send_to_telegram_user(message)

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
