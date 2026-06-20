from typing import Any

import structlog

from channels.signal_channel.sig_bot_manager import SignalBotManager
from channels.signal_channel.sig_envelope_factory import SignalEnvelopeFactory
from channels.signal_channel.sig_transport import SignalTransport
from channels.signal_channel.plugin_settings import SignalSettings
from src import (
    ConnectorNotFoundError,
    Envelope,
    IdempotencyKeyAlreadyProcessedError,
    PGMessageQueue,
)

logger = structlog.get_logger(__name__)


class SignalMessageProcessor:
    """Processes Signal->Chatwoot and Chatwoot->Signal messages."""

    def __init__(
        self,
        bot_manager: SignalBotManager,
        transport: SignalTransport,
        envelope_factory: SignalEnvelopeFactory,
        settings: SignalSettings,
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

    async def build_channel_message(
        self, raw_data: dict[str, Any]
    ) -> tuple[str, Envelope]:
        connector_id = str(raw_data["connector_id"])
        channel = str(raw_data["channel"])
        # Text-only: no attachment download step (unlike Telegram/iMessage).
        return self._envelope_factory.parse_channel_request(
            raw_data, connector_id, channel
        )

    async def publish_channel_message(
        self, idempotency_key: str, envelope: Envelope, raw_data: dict[str, Any]
    ) -> None:
        connector_id = str(raw_data["connector_id"])
        self._get_required_client(connector_id)
        if await self._is_already_processed(idempotency_key):
            raise IdempotencyKeyAlreadyProcessedError(
                "Idempotency key has already been processed."
            )
        await self._process_queue(self._iqn, idempotency_key, envelope)

    async def publish_chatwoot_message(
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

    def _get_required_client(self, connector_id: str) -> Any:
        try:
            return self._bot_manager.get_client_by_connector_id(connector_id)
        except KeyError as exc:
            raise ConnectorNotFoundError(
                f"Unknown connector_id={connector_id}"
            ) from exc

    async def _is_already_processed(self, idempotency_key: str) -> bool:
        return await self._mq.is_already_processed(idempotency_key)

    async def _process_queue(
        self, queue_name: str, idempotency_key: str, envelope: Envelope
    ) -> None:
        payload = envelope.model_dump(mode="json")
        await self._mq.send(queue_name, payload)
        await self._mq.mark_as_processed(idempotency_key)
