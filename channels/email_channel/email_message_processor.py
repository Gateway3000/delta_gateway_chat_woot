from typing import Any

import structlog

from channels.email_channel.email_attachments import (
    prepare_email_to_chatwoot_attachments,
)
from channels.email_channel.email_envelope_factory import EmailEnvelopeFactory
from channels.email_channel.email_imap_client import EmailImapClient
from src import Envelope, IdempotencyKeyAlreadyProcessedError, PGMessageQueue
from src.multichannel_gateway.infrastructure.endpoints import handle_channel_payload

logger = structlog.get_logger(__name__)


class EmailMessageProcessor:
    """Processes normalized Email payloads for Channel -> Chatwoot flow."""

    def __init__(
        self,
        envelope_factory: EmailEnvelopeFactory,
        imap_client: EmailImapClient,
        mq: PGMessageQueue,
        incoming_queue_name: str,
        outgoing_queue_name: str,
    ) -> None:
        self._envelope_factory = envelope_factory
        self._imap_client = imap_client
        self._mq = mq
        self._iqn = incoming_queue_name
        self._oqn = outgoing_queue_name

    async def build_channel_message(
        self, raw_data: dict[str, Any]
    ) -> tuple[str, Envelope]:
        connector_id = str(raw_data["connector_id"])
        channel = str(raw_data["channel"])
        idempotency_key, envelope = self._envelope_factory.parse_channel_request(
            raw_data, connector_id, channel
        )
        prepared_payload = prepare_email_to_chatwoot_attachments(
            envelope.model_dump(mode="json")
        )
        return idempotency_key, Envelope.model_validate(prepared_payload)

    async def publish_channel_message(
        self, idempotency_key: str, envelope: Envelope
    ) -> None:
        if await self._mq.is_already_processed(idempotency_key):
            raise IdempotencyKeyAlreadyProcessedError(
                "Idempotency key has already been processed."
            )
        await self._process_queue(self._iqn, idempotency_key, envelope)

    async def _process_queue(
        self, queue_name: str, idempotency_key: str, envelope: Envelope
    ) -> None:
        try:
            payload = envelope.model_dump(mode="json")
            await self._mq.send(queue_name, payload)
            await self._mq.mark_as_processed(idempotency_key)
        except Exception as e:
            logger.error(f"Exception occurred: {str(e)}")

    async def publish_chatwoot_message(
        self, raw_data: dict[str, Any], cw_account_id: str, channel: str
    ) -> None:
        idempotency_key, envelope = self._envelope_factory.parse_chatwoot_request(
            raw_data, cw_account_id, channel
        )
        if await self._mq.is_already_processed(idempotency_key):
            raise IdempotencyKeyAlreadyProcessedError(
                "Idempotency key has already been processed."
            )
        await self._process_queue(self._oqn, idempotency_key, envelope)

    async def poll_once(self) -> None:
        payloads = await self._imap_client.fetch_inbound_payloads()
        for payload in payloads:
            connector_id = payload["connector_id"]
            try:
                await handle_channel_payload("email", connector_id, payload)
            except Exception as e:
                logger.error(
                    "Failed to process IMAP payload", error=str(e), payload=payload
                )
