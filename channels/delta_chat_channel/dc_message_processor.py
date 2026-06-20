from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from channels.delta_chat_channel.dc_routing import DeltaChatRouting
from channels.delta_chat_channel.dc_transport import DeltaChatTransport
from src import (
    ChannelDeliveryResult,
    Envelope,
    IdempotencyKeyAlreadyProcessedError,
    PGMessageQueue,
    SenderInfo,
)
from src.multichannel_gateway.app.chatwoot_attachments import extract_chatwoot_attachments
from src.multichannel_gateway.core.interfaces.envelope_factory import IEnvelopeFactory
from src.multichannel_gateway.infrastructure.identity_store import IdentityStore


class DeltaChatMessageProcessor:
    def __init__(
        self,
        routing: DeltaChatRouting,
        transport: DeltaChatTransport,
        identity_store: IdentityStore,
        mq: PGMessageQueue,
        incoming_queue_name: str,
        outgoing_queue_name: str,
    ) -> None:
        self._routing = routing
        self._transport = transport
        self._identity_store = identity_store
        self._mq = mq
        self._iqn = incoming_queue_name
        self._oqn = outgoing_queue_name

    async def build_channel_message(
        self, raw_data: dict[str, Any]
    ) -> tuple[str, Envelope]:
        account_id = raw_data.get("account_id")
        connector_id = (
            str(raw_data["connector_id"])
            if raw_data.get("connector_id")
            else self._routing.get_connector_id_by_account_id(account_id)
            if account_id is not None
            else self._routing.get_default_connector_id()
        )
        route = self._routing.get_route_by_connector_id(connector_id)

        external_id = self._required_str(raw_data, "sender_address")
        actor_id = await self._identity_store.get_or_create_actor_id(
            "delta_chat", external_id
        )
        message_id = self._required_str(raw_data, "message_id")
        chat_id = self._required_str(raw_data, "chat_id")
        text = str(raw_data.get("text") or "")
        attachments = list(raw_data.get("attachments") or [])

        idempotency_key = IEnvelopeFactory.build_idempotency_key(
            direction="delta_chat->chatwoot",
            connector_id=route["connector_id"],
            external_id=external_id,
            message_id=message_id,
            account_id=str(account_id or ""),
            chat_id=chat_id,
        )

        envelope = Envelope(
            idem_key=idempotency_key,
            channel="delta_chat",
            from_="delta_chat",
            to="chatwoot",
            connector_id=route["connector_id"],
            cw_inbox_id=route["cw_inbox_id"],
            cw_account_id=route["cw_account_id"],
            message_id=message_id,
            sender=SenderInfo(
                external_id=actor_id,
                raw_external_id=external_id,
                name=raw_data.get("sender_name"),
                nickname=raw_data.get("sender_name"),
            ),
            payload={
                "text": text,
                "attachments": attachments,
                "chat_id": chat_id,
                "account_id": account_id,
                "is_group": bool(raw_data.get("is_group")),
            },
            ts=float(datetime.now().timestamp()),
        )
        return idempotency_key, envelope

    async def publish_channel_message(
        self, idempotency_key: str, envelope: Envelope, raw_data: dict[str, Any]
    ) -> None:
        if await self._mq.is_already_processed(idempotency_key):
            raise IdempotencyKeyAlreadyProcessedError(
                "Idempotency key has already been processed."
            )
        await self._mq.send(self._iqn, envelope.model_dump(mode="json"))
        await self._mq.mark_as_processed(idempotency_key)

    async def publish_chatwoot_message(
        self, raw_data: dict[str, Any], cw_account_id: str
    ) -> None:
        inbox_id = str(raw_data["inbox"]["id"])
        route = self._routing.get_route_by_inbox_id(inbox_id)
        actor_id = str(raw_data["conversation"]["meta"]["sender"]["identifier"])
        message_id = str(raw_data["conversation"]["messages"][0]["id"])
        attachments = extract_chatwoot_attachments(raw_data)

        idempotency_key = IEnvelopeFactory.build_idempotency_key(
            direction="chatwoot->delta_chat",
            connector_id=route["connector_id"],
            external_id=actor_id,
            message_id=message_id,
        )
        envelope = Envelope(
            idem_key=idempotency_key,
            channel="delta_chat",
            from_="chatwoot",
            to="delta_chat",
            connector_id=route["connector_id"],
            cw_inbox_id=inbox_id,
            cw_account_id=cw_account_id,
            message_id=message_id,
            sender=SenderInfo(external_id=actor_id),
            payload={
                "text": str(raw_data.get("content") or ""),
                "attachments": attachments,
            },
            ts=float(datetime.now().timestamp()),
        )

        if not await self._mq.is_already_processed(idempotency_key):
            await self._mq.send(self._oqn, envelope.model_dump(mode="json"))
            await self._mq.mark_as_processed(idempotency_key)
        else:
            raise IdempotencyKeyAlreadyProcessedError(
                "Idempotency key has already been processed."
            )

    async def send_to_user(
        self, message: dict[str, Any], limiter: Any = None
    ) -> ChannelDeliveryResult:
        return await self._transport.send_to_delta_chat_user(message)

    @staticmethod
    def _required_str(raw_data: dict[str, Any], key: str) -> str:
        value = raw_data.get(key)
        if value is None or value == "":
            raise ValueError(f"Missing required key: {key}")
        return str(value)

    @staticmethod
    def _resolve_message_id(
        raw_data: dict[str, Any],
        conversation_id: str,
        text: str,
        attachments: list[dict[str, Any]],
    ) -> str:
        if message_id := raw_data.get("message_id"):
            return str(message_id)
        digest_input = json.dumps(
            {
                "conversation_id": conversation_id,
                "text": text,
                "attachments": attachments,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha1(digest_input.encode("utf-8")).hexdigest()

