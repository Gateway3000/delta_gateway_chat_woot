from typing import Any

from aiogram import Bot

from core.exceptions import ConnectorNotFoundError, WrongUpdateTypeError
from core.interfaces.message_queue import IMessageQueue
from infrastructure.pydantic_models import Envelope
from infrastructure.telegram.tg_adapter import TelegramAdapter
from infrastructure.telegram.tg_bot_manager import TelegramBotManager
from infrastructure.telegram.tg_routing import TelegramRouting
from infrastructure.telegram.tg_transport import TelegramTransport


class TelegramIOProcessor:
    """Subsystem for processing inbound and outbound Telegram messages.

    This class is responsible for handling the full lifecycle of Telegram message
    exchange — receiving, normalizing, routing, and delivering messages between
    the Telegram channel and internal systems (e.g., Chatwoot or Gateway).
    """

    def __init__(
        self,
        bot_manager: TelegramBotManager,
        routing: TelegramRouting,
        transport: TelegramTransport,
        adapter: TelegramAdapter,
        mq: IMessageQueue,
        incoming_queue_name: str,
        outgoing_queue_name: str,
    ) -> None:
        self._bot_manager = bot_manager
        self._routing = routing
        self._transport = transport
        self._adapter = adapter
        self._mq = mq
        self._iqn = incoming_queue_name
        self._oqn = outgoing_queue_name

    async def process_inbound(
        self, connector_id: str, raw_data: dict[str, Any], channel: str
    ) -> None:
        bot = self._get_required_bot(connector_id)
        route = self._routing.get_route_by_connector_id(connector_id)

        message = raw_data.get("message")
        if not message:
            raise WrongUpdateTypeError("Wrong update type")

        envelope, idempotency_key = self._build_envelope(message, route, channel)
        if not await self._is_already_processed(idempotency_key):
            await self._process_queue(self._iqn, idempotency_key, envelope)
            await self._transport.send_to_telegram(bot, raw_data)

    async def process_outbound(
        self, cw_account_id: str, raw_data: dict[str, Any], channel: str
    ) -> None:
        route = self._routing.get_route_by_cw_account_id(cw_account_id)
        envelope, idempotency_key = self._build_envelope(raw_data, route, channel)

        if not await self._is_already_processed(idempotency_key):
            await self._process_queue(self._oqn, idempotency_key, envelope)

    def _get_required_bot(self, connector_id: str) -> Bot:
        if bot := self._bot_manager.get_bot_by_connector_id(connector_id):
            return bot
        raise ConnectorNotFoundError(f"Unknown connector_id={connector_id}")

    def _build_envelope(
        self, raw_data: dict[str, Any], route: dict[str, str], channel: str
    ) -> tuple[Envelope, str]:
        idempotency_key = self._adapter.idempotency_key(raw_data, route)
        envelope = self._adapter.normalize_inbound(
            raw=raw_data, route=route, idempotency_key=idempotency_key, channel=channel
        )
        return envelope, idempotency_key

    async def _is_already_processed(self, idempotency_key: str) -> bool:
        return await self._mq.is_already_processed(idempotency_key)

    async def _process_queue(
        self, queue_name: str, idempotency_key: str, envelope: Envelope
    ) -> None:
        payload = envelope.model_dump_json()
        await self._mq.send(queue_name, payload)
        await self._mq.mark_as_processed(idempotency_key)
