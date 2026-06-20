from typing import Any

import structlog

from channels.whatsapp_channel.plugin_settings import WhatsAppSettings
from channels.whatsapp_channel.wa_attachments import (
    prepare_whatsapp_to_chatwoot_attachments,
)
from channels.whatsapp_channel.wa_envelope_factory import WhatsAppEnvelopeFactory
from src import Envelope, IdempotencyKeyAlreadyProcessedError, PGMessageQueue

logger = structlog.get_logger(__name__)


class WhatsAppMessageProcessor:
    def __init__(
        self,
        envelope_factory: WhatsAppEnvelopeFactory,
        settings: WhatsAppSettings,
        mq: PGMessageQueue,
        incoming_queue_name: str,
        outgoing_queue_name: str,
    ) -> None:
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
        idem_key, envelope = self._envelope_factory.parse_channel_request(
            raw_data, connector_id, channel
        )
        prepared = await prepare_whatsapp_to_chatwoot_attachments(
            envelope.model_dump(mode="json")["payload"],
            sidecar_token=self._settings.sidecar_token,
            max_mb=self._settings.chatwoot_upload_max_mb,
        )
        envelope = envelope.model_copy(update={"payload": prepared})
        return idem_key, envelope

    async def publish_channel_message(self, idem_key: str, envelope: Envelope) -> None:
        if await self._mq.is_already_processed(idem_key):
            raise IdempotencyKeyAlreadyProcessedError(idem_key)
        await self._process_queue(self._iqn, idem_key, envelope)

    async def publish_chatwoot_message(
        self, raw_data: dict[str, Any], cw_account_id: str, channel: str
    ) -> None:
        idem_key, envelope = self._envelope_factory.parse_chatwoot_request(
            raw_data, cw_account_id, channel
        )
        if await self._mq.is_already_processed(idem_key):
            raise IdempotencyKeyAlreadyProcessedError(idem_key)
        await self._process_queue(self._oqn, idem_key, envelope)

    async def _process_queue(
        self, queue_name: str, idem_key: str, envelope: Envelope
    ) -> None:
        payload = envelope.model_dump(mode="json")
        await self._mq.send(queue_name, payload)
        await self._mq.mark_as_processed(idem_key)
