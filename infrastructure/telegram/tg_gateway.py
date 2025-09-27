from typing import Any

from aiogram import Bot

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
        adapter: TelegramAdapter,
        io_processor: TelegramIOProcessor,
    ) -> None:
        self._bot_manager = bot_manager
        self._routing = routing
        self._wh_manager = webhook_manager
        self._transport = transport
        self._adapter = adapter
        self._io_processor = io_processor

    def get_bot(self, connector_id: str) -> Bot:
        return self._bot_manager.get_bot_by_connector_id(connector_id)

    async def close_bot_sessions(self) -> None:
        await self._bot_manager.close_sessions()

    def get_route_by_connector_id(self, connector_id: str) -> dict[str, str]:
        return self._routing.get_route_by_connector_id(connector_id)

    def get_route_by_cw_account_id(self, cw_account_id: str) -> dict[str, str]:
        return self._routing.get_route_by_cw_account_id(cw_account_id)

    def get_connector_id(self, cw_account_id: str) -> str:
        return self._routing.get_connector_id(cw_account_id)

    async def set_webhooks(self) -> None:
        await self._wh_manager.set_wh()

    async def send_to_telegram(self, bot: Bot, raw_data: dict[str, Any]) -> None:
        await self._transport.send_to_telegram(bot, raw_data)

    async def send_to_user(
        self, message: dict[str, Any], limiter: Any = None
    ) -> DeliveryResult:
        return await self._transport.send_to_user(message)

    async def process_inbound(
        self, connector_id: str, raw_data: dict[str, Any]
    ) -> None:
        await self._io_processor.process_inbound(connector_id, raw_data, self.channel)

    async def process_outbound(
        self, cw_account_id: str, raw_data: dict[str, Any]
    ) -> None:
        await self._io_processor.process_outbound(cw_account_id, raw_data, self.channel)
