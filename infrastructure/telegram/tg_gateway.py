from typing import Any


from core.interfaces.gateway import IGateway
from infrastructure.pydantic_models import DeliveryResult
from infrastructure.telegram.tg_adapter import TelegramAdapter
from infrastructure.telegram.tg_bot_manager import TelegramBotManager
from infrastructure.telegram.tg_io_processor import TelegramIOProcessor
from infrastructure.telegram.tg_routing import TelegramRouting
from infrastructure.telegram.tg_transport import TelegramTransport
from infrastructure.telegram.tg_wh_manager import TelegramWebhookManager


class TelegramGateway(IGateway):
    channel = "telegram"

    def __init__(
        self,
        bot_manager: TelegramBotManager,
        routing: TelegramRouting,
        webhook_manager: TelegramWebhookManager,
        transport: TelegramTransport,
        io_processor: TelegramIOProcessor,
        adapter: TelegramAdapter,
    ) -> None:
        self._bot_manager = bot_manager
        self._routing = routing
        self._wh_manager = webhook_manager
        self._transport = transport
        self._io_processor = io_processor
        self._adapter = adapter

    async def close_bot_sessions(self) -> None:
        await self._bot_manager.close_sessions()

    def get_route_by_connector_id(self, connector_id: str) -> dict[str, str]:
        return self._routing.get_route_by_connector_id(connector_id)

    async def set_webhooks(self) -> None:
        await self._wh_manager.set_wh()

    async def send_to_user(
        self, message: dict[str, Any], limiter: Any = None
    ) -> DeliveryResult:
        return await self._transport.send_to_user(message)

    async def process_inbound(
        self,
        raw_data: dict[str, Any],
        connector_id: str,
    ) -> None:
        await self._io_processor.process_inbound(raw_data, connector_id, self.channel)

    async def process_outbound(
        self, raw_data: dict[str, Any], cw_account_id: str
    ) -> None:
        await self._io_processor.process_outbound(
            raw_data,
            cw_account_id,
            self.channel,
        )
