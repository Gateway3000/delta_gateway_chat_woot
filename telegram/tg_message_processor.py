from typing import Any

import structlog
from aiogram import Bot

from src import (
    PGMessageQueue,
    Envelope,
    IdempotencyKeyAlreadyProcessedError,
    ConnectorNotFoundError,
)
from telegram.plugin_settings import TelegramSettings
from telegram.tg_attachments import prepare_inbound_attachments
from telegram.tg_bot_manager import TelegramBotManager
from telegram.tg_envelope_factory import TelegramEnvelopeFactory
from telegram.tg_transport import TelegramTransport

logger = structlog.get_logger(__name__)


class TelegramMessageProcessor:
    """Processes inbound and outbound Telegram messages."""

    def __init__(
        self,
        bot_manager: TelegramBotManager,
        transport: TelegramTransport,
        envelope_factory: TelegramEnvelopeFactory,
        settings: TelegramSettings,
        mq: PGMessageQueue,
        incoming_queue_name: str,
        outgoing_queue_name: str,
    ) -> None:
        self._bot_manager = bot_manager
        self._transport = transport
        self._envelope_factory = envelope_factory
        self._settings = settings
        self._mq = mq
        self._iqn = incoming_queue_name
        self._oqn = outgoing_queue_name

    @staticmethod
    async def _send_delivery_confirmation(bot: Bot, raw_data: dict[str, Any]) -> None:
        await bot.send_message(
            chat_id=raw_data["message"]["chat"]["id"],
            text="Your message was sent successfully!",
        )

    async def process_inbound(self, raw_data: dict[str, Any]) -> None:
        connector_id = str(raw_data["connector_id"])
        channel = str(raw_data["channel"])
        idempotency_key, envelope = self._envelope_factory.parse_channel_request(
            raw_data, connector_id, channel
        )
        bot = self._get_required_bot(connector_id)
        if not await self._is_already_processed(idempotency_key):
            prepared_payload = await prepare_inbound_attachments(
                envelope.model_dump(mode="json"),
                bot_manager=self._bot_manager,
                settings=self._settings,
            )
            envelope = Envelope.model_validate(prepared_payload)
            await self._process_queue(self._iqn, idempotency_key, envelope)
            await self._send_delivery_confirmation(bot, raw_data)
        else:
            raise IdempotencyKeyAlreadyProcessedError(
                "Idempotency key has already been processed."
            )

    async def process_outbound(
        self, raw_data: dict[str, Any], cw_account_id: str, channel: str
    ) -> None:
        idempotency_key, envelope = self._envelope_factory.parse_chatwoot_request(
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
        payload = envelope.model_dump(mode="json")
        await self._mq.send(queue_name, payload)
        await self._mq.mark_as_processed(idempotency_key)
