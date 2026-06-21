from datetime import datetime
from typing import Any

from channels.simplex_channel.sx_routing import SimplexRouting
from src import Envelope, SenderInfo
from src.multichannel_gateway import WrongUpdateTypeError
from src.multichannel_gateway.core.interfaces.envelope_factory import IEnvelopeFactory


class SimplexEnvelopeFactory(IEnvelopeFactory):
    def __init__(self, routing: SimplexRouting) -> None:
        self._routing = routing

    def parse_channel_request(
        self, raw_data: dict[str, Any], connector_id: str, channel: str
    ) -> tuple[str, Envelope]:
        route = self._routing.get_route_by_connector_id(connector_id)

        # The connection normalizes simplex-chat `newChatItems` events to
        # {"type":"message","source_id":..,"source_name":..,"item_id":..,"text":..}
        # and already filters to 1:1 received text. We re-check defensively.
        if raw_data.get("type") != "message":
            raise WrongUpdateTypeError
        source_id = raw_data.get("source_id")
        text = str(raw_data.get("message") or raw_data.get("text") or "").strip()
        item_id = raw_data.get("item_id")
        if source_id is None or not text or item_id is None:
            raise WrongUpdateTypeError

        # The SimpleX chat item id uniquely identifies the message; use it as
        # the idempotency anchor.
        message_id = str(item_id)
        to = "chatwoot"

        sender_info = SenderInfo(
            # The SimpleX contact id is the reply address (used as "@<id>").
            external_id=str(source_id),
            name=raw_data.get("source_name") or str(source_id),
            nickname=str(source_id),
        )

        idempotency_key = self.build_idempotency_key(
            direction=f"{channel}->{to}",
            connector_id=route["connector_id"],
            external_id=sender_info["external_id"],
            message_id=message_id,
            # SimpleX has no token; the CLI user id fingerprints the connector.
            user_suffix=route["user_id"],
        )

        envelope = Envelope(
            idem_key=idempotency_key,
            channel=channel,
            from_=channel,
            to=to,
            connector_id=route["connector_id"],
            cw_inbox_id=route["cw_inbox_id"],
            cw_account_id=route["cw_account_id"],
            message_id=message_id,
            sender=sender_info,
            payload={"text": text, "attachments": [], "raw_data": raw_data},
            ts=float(datetime.now().timestamp()),
        )
        return envelope.idem_key, envelope

    def parse_chatwoot_request(
        self, raw_data: dict[str, Any], cw_account_id: str, channel: str
    ) -> tuple[str, Envelope]:
        route = self._routing.get_route_by_inbox_id(str(raw_data["inbox"]["id"]))
        # The identifier Chatwoot stores is the SimpleX contact id.
        recipient = raw_data["conversation"]["meta"]["sender"]["identifier"]
        sender_info = SenderInfo(external_id=recipient)
        message_id = str(raw_data["conversation"]["messages"][0]["id"])
        from_ = "chatwoot"

        idempotency_key = self.build_idempotency_key(
            direction=f"{from_}->{channel}",
            connector_id=route["connector_id"],
            external_id=sender_info["external_id"],
            message_id=message_id,
            user_suffix=route["user_id"],
        )

        envelope = Envelope(
            idem_key=idempotency_key,
            channel=channel,
            from_=from_,
            to=channel,
            connector_id=route["connector_id"],
            cw_inbox_id=str(raw_data["inbox"]["id"]),
            cw_account_id=cw_account_id,
            message_id=message_id,
            sender=sender_info,
            payload={"text": raw_data.get("content", ""), "attachments": []},
            ts=float(datetime.now().timestamp()),
        )
        return envelope.idem_key, envelope
