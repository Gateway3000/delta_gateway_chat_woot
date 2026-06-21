from typing import Any

import structlog

from channels.imessage_channel.im_attachments import (
    prepare_imessage_to_chatwoot_attachments,
)
from channels.imessage_channel.im_bot_manager import IMessageBotManager
from channels.imessage_channel.im_envelope_factory import IMessageEnvelopeFactory
from channels.imessage_channel.im_transport import IMessageTransport
from channels.imessage_channel.plugin_settings import IMessageSettings
from src import (
    PGMessageQueue,
    Envelope,
    IdempotencyKeyAlreadyProcessedError,
    ConnectorNotFoundError,
)

logger = structlog.get_logger(__name__)


class IMessageMessageProcessor:
    """Processes iMessage->Chatwoot and Chatwoot->iMessage messages."""

    def __init__(
        self,
        bot_manager: IMessageBotManager,
        transport: IMessageTransport,
        envelope_factory: IMessageEnvelopeFactory,
        settings: IMessageSettings,
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

    async def _send_delivery_confirmation(
        self, connector_id: str, raw_data: dict[str, Any]
    ) -> None:
        client = self._get_required_client(connector_id)
        chat_guid = self._envelope_factory._get_chat_guid(raw_data)
        await client.send_text(
            chat_guid,
            "Your message was sent successfully!",
            temp_guid=f"confirm-{chat_guid}",
        )

    async def build_channel_message(
        self, raw_data: dict[str, Any]
    ) -> tuple[str, Envelope]:
        connector_id = str(raw_data["connector_id"])
        channel = str(raw_data["channel"])
        idempotency_key, envelope = self._envelope_factory.parse_channel_request(
            raw_data, connector_id, channel
        )
        prepared_payload = await prepare_imessage_to_chatwoot_attachments(
            envelope.model_dump(mode="json"),
            bot_manager=self._bot_manager,
            settings=self._settings,
        )
        return idempotency_key, Envelope.model_validate(prepared_payload)

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
        if self._settings.enable_channel_delivery_confirmation:
            await self._send_delivery_confirmation(connector_id, raw_data)

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

    def _get_required_client(self, connector_id: str):
        if client := self._bot_manager.get_client_by_connector_id(connector_id):
            return client
        raise ConnectorNotFoundError(f"Unknown connector_id={connector_id}")

    async def _is_already_processed(self, idempotency_key: str) -> bool:
        return await self._mq.is_already_processed(idempotency_key)

    async def _process_queue(
        self, queue_name: str, idempotency_key: str, envelope: Envelope
    ) -> None:
        payload = envelope.model_dump(mode="json")
        await self._mq.send(queue_name, payload)
        await self._mq.mark_as_processed(idempotency_key)
