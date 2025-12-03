from typing import Any

import structlog
from aiogram import Bot

from src.multichannel_gateway.core.exceptions import (
    ConnectorNotFoundError,
    IdempotencyKeyAlreadyProcessedError,
)
from src.multichannel_gateway.core.interfaces.message_queue import IMessageQueue
from src.multichannel_gateway.infrastructure.pydantic_models import Envelope
from telegram.tg_adapter import TelegramAdapter
from telegram.tg_bot_manager import TelegramBotManager
from telegram.tg_transport import TelegramTransport

logger = structlog.get_logger(__name__)


class TelegramIOProcessor:
    """Subsystem for processing inbound and outbound Telegram messages.

    This class is responsible for handling the full lifecycle of Telegram message
    exchange — receiving, normalizing, routing, and delivering messages between
    the Telegram channel and internal systems (e.g., Chatwoot or Gateway).
    """

    def __init__(
        self,
        bot_manager: TelegramBotManager,
        transport: TelegramTransport,
        adapter: TelegramAdapter,
        mq: IMessageQueue,
        incoming_queue_name: str,
        outgoing_queue_name: str,
    ) -> None:
        self._bot_manager = bot_manager
        self._transport = transport
        self._adapter = adapter
        self._mq = mq
        self._iqn = incoming_queue_name
        self._oqn = outgoing_queue_name

    async def process_inbound(
        self, raw_data: dict[str, Any], connector_id: str, channel: str
    ) -> None:
        idempotency_key, envelope = self._adapter.parse_channel_request(
            raw_data, connector_id, channel
        )
        bot = self._get_required_bot(connector_id)
        if not await self._is_already_processed(idempotency_key):
            await self._process_queue(self._iqn, idempotency_key, envelope)
            await self._transport.send_to_telegram(bot, raw_data)
        else:
            raise IdempotencyKeyAlreadyProcessedError(
                "Idempotency key has already been processed."
            )

    async def process_outbound(
        self, raw_data: dict[str, Any], cw_account_id: str, channel: str
    ) -> None:
        idempotency_key, envelope = self._adapter.parse_chatwoot_request(
            raw_data, cw_account_id, channel
        )

        if not await self._is_already_processed(idempotency_key):
            await self._process_queue(self._oqn, idempotency_key, envelope)
        else:
            raise IdempotencyKeyAlreadyProcessedError(
                "Idempotency key has already been processed."
            )

    def _get_required_bot(self, connector_id: str) -> Bot:
        if bot := self._bot_manager.get_bot_by_connector_id(connector_id):
            return bot
        raise ConnectorNotFoundError(f"Unknown connector_id={connector_id}")

    async def _is_already_processed(self, idempotency_key: str) -> bool:
        return await self._mq.is_already_processed(idempotency_key)

    async def _process_queue(
        self, queue_name: str, idempotency_key: str, envelope: Envelope
    ) -> None:
        payload = envelope.model_dump_json()
        await self._mq.send(queue_name, payload)
        await self._mq.mark_as_processed(idempotency_key)
