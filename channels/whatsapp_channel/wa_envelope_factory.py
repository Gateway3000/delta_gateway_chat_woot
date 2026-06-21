from datetime import datetime
from typing import Any

from channels.whatsapp_channel.wa_routing import WhatsAppRouting
from src import Envelope, SenderInfo
from src.multichannel_gateway import WrongUpdateTypeError
from src.multichannel_gateway.app.chatwoot_attachments import (
    extract_chatwoot_attachments,
)
from src.multichannel_gateway.core.interfaces.envelope_factory import IEnvelopeFactory


class WhatsAppEnvelopeFactory(IEnvelopeFactory):
    """Parses sidecar inbound JSON and Chatwoot webhooks into Envelopes.

    Inbound payload shape (posted by the Baileys sidecar):
        {
          "message_id": "...",
          "from": {"id": "<jid>@s.whatsapp.net", "name": "pushName"},
          "text": "...",
          "timestamp": 1710000000,
          "attachments": [{"id","type","mimetype","filename","url"}]
        }
    """

    def __init__(self, routing: WhatsAppRouting) -> None:
        self._routing = routing

    def parse_channel_request(
        self, raw_data: dict[str, Any], connector_id: str, channel: str
    ) -> tuple[str, Envelope]:
        route = self._routing.get_route_by_connector_id(connector_id)

        sender = raw_data.get("from") or {}
        external_id = sender.get("id")
        if not external_id:
            raise WrongUpdateTypeError("whatsapp: missing sender id")

        message_id = str(raw_data.get("message_id") or "")
        if not message_id:
            raise WrongUpdateTypeError("whatsapp: missing message_id")

        sender_info = SenderInfo(
            external_id=external_id,
            name=sender.get("name") or "",
        )

        idem_key = self.build_idempotency_key(
            direction=f"{channel}->chatwoot",
            connector_id=route["connector_id"],
            external_id=str(external_id),
            message_id=message_id,
        )

        envelope = Envelope(
            idem_key=idem_key,
            channel=channel,
            from_=channel,
            to="chatwoot",
            connector_id=route["connector_id"],
            cw_inbox_id=route["cw_inbox_id"],
            cw_account_id=route["cw_account_id"],
            message_id=message_id,
            sender=sender_info,
            payload={
                "text": raw_data.get("text", ""),
                # raw sidecar attachments (with url); prepared in the processor
                "attachments": raw_data.get("attachments", []),
            },
            ts=float(raw_data.get("timestamp") or datetime.now().timestamp()),
        )
        return idem_key, envelope

    def parse_chatwoot_request(
        self, raw_data: dict[str, Any], cw_account_id: str, channel: str
    ) -> tuple[str, Envelope]:
        route = self._routing.get_route_by_inbox_id(str(raw_data["inbox"]["id"]))
        identifier = raw_data["conversation"]["meta"]["sender"]["identifier"]
        sender_info = SenderInfo(external_id=identifier)
        message_id = str(raw_data["conversation"]["messages"][0]["id"])
        attachments = extract_chatwoot_attachments(raw_data)

        idem_key = self.build_idempotency_key(
            direction=f"chatwoot->{channel}",
            connector_id=route["connector_id"],
            external_id=str(identifier),
            message_id=message_id,
        )

        envelope = Envelope(
            idem_key=idem_key,
            channel=channel,
            from_="chatwoot",
            to=channel,
            connector_id=route["connector_id"],
            cw_inbox_id=str(raw_data["inbox"]["id"]),
            cw_account_id=cw_account_id,
            message_id=message_id,
            sender=sender_info,
            payload={"text": raw_data.get("content", ""), "attachments": attachments},
            ts=float(datetime.now().timestamp()),
        )
        return idem_key, envelope
