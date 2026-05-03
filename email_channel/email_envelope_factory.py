from __future__ import annotations

from datetime import datetime
from typing import Any

from email_channel.email_routing import EmailRouting
from src import Envelope, SenderInfo
from src.multichannel_gateway.app.chatwoot_attachments import (
    extract_chatwoot_attachments,
)
from src.multichannel_gateway.core.base_envelope_factory import BaseEnvelopeFactory


class EmailEnvelopeFactory(BaseEnvelopeFactory):
    """Builds Envelope models from normalized inbound email payloads."""

    def __init__(self, routing: EmailRouting) -> None:
        self._routing = routing

    def parse_channel_request(
        self, raw_data: dict[str, Any], connector_id: str, channel: str
    ) -> tuple[str, Envelope]:
        route = self._routing.get_route_by_connector_id(connector_id)

        sender = self._parse_sender(raw_data)
        message_id = self._resolve_message_id(raw_data)
        uid = self._required_str(raw_data, "uid")
        uidvalidity = self._required_str(raw_data, "uidvalidity")
        idem_key = self._build_idempotency_key(
            direction=f"{channel}->chatwoot",
            connector_id=route["connector_id"],
            external_id=sender["external_id"],
            message_id=message_id,
            imap_mailbox=route["imap_mailbox"],
            uidvalidity=uidvalidity,
            uid=uid,
        )

        payload = {
            "text": str(
                f"Subject: {raw_data.get('subject') or 'No subject'}\n\n{raw_data.get('text') or ''}"
            ),
            "html": str(raw_data.get("html") or ""),
            "attachments": raw_data.get("attachments", []),
            "raw_headers": raw_data.get("raw_headers", {}),
        }

        envelope = Envelope(
            idem_key=idem_key,
            channel=channel,
            from_=channel,
            to="chatwoot",
            connector_id=route["connector_id"],
            cw_inbox_id=route["cw_inbox_id"],
            cw_account_id=route["cw_account_id"],
            message_id=message_id,
            sender=sender,
            payload=payload,
            ts=float(datetime.now().timestamp()),
        )
        return idem_key, envelope

    def parse_chatwoot_request(
        self, raw_data: dict[str, Any], cw_account_id: str, channel: str
    ) -> tuple[str, Envelope]:
        inbox_id = str(raw_data["inbox"]["id"])
        route = self._routing.get_route_by_inbox_id(inbox_id)
        sender_external_id = str(
            raw_data["conversation"]["meta"]["sender"]["identifier"]
        )
        sender_info = SenderInfo(external_id=sender_external_id)
        message_id = str(raw_data["conversation"]["messages"][0]["id"])
        idempotency_key = self._build_idempotency_key(
            direction=f"chatwoot->{channel}",
            connector_id=route["connector_id"],
            external_id=sender_external_id,
            message_id=message_id,
        )
        attachments = extract_chatwoot_attachments(raw_data)

        envelope = Envelope(
            idem_key=idempotency_key,
            channel=channel,
            from_="chatwoot",
            to=channel,
            connector_id=route["connector_id"],
            cw_inbox_id=inbox_id,
            cw_account_id=cw_account_id,
            message_id=message_id,
            sender=sender_info,
            payload={
                "subject": str(raw_data.get("subject") or ""),
                "text": str(raw_data.get("content") or ""),
                "attachments": attachments,
            },
            ts=float(datetime.now().timestamp()),
        )
        return idempotency_key, envelope

    @staticmethod
    def _required_str(raw_data: dict[str, Any], key: str) -> str:
        value = raw_data.get(key)
        if value is None:
            raise ValueError(f"Missing required key: {key}")
        return str(value)

    @staticmethod
    def _resolve_message_id(raw_data: dict[str, Any]) -> str:
        if message_id := raw_data.get("message_id"):
            return str(message_id)

        uid = raw_data.get("uid")
        if uid is None:
            raise ValueError("Either message_id or uid must be present")
        return f"uid:{uid}"

    @staticmethod
    def _parse_sender(raw_data: dict[str, Any]) -> SenderInfo:
        sender = raw_data.get("sender", {})
        email = str(sender.get("email") or "").strip()
        if not email:
            raise ValueError("sender.email is required")

        return SenderInfo(
            external_id=email.lower(),
            name=(str(sender.get("name") or "").strip() or None),
            nickname=email.split("@", 1)[0] if "@" in email else None,
        )
