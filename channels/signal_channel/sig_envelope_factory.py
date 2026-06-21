from datetime import datetime
from typing import Any

from channels.signal_channel.sig_routing import SignalRouting
from src import Envelope, SenderInfo
from src.multichannel_gateway import WrongUpdateTypeError
from src.multichannel_gateway.core.interfaces.envelope_factory import IEnvelopeFactory


class SignalEnvelopeFactory(IEnvelopeFactory):
    def __init__(self, routing: SignalRouting) -> None:
        self._routing = routing

    def parse_channel_request(
        self, raw_data: dict[str, Any], connector_id: str, channel: str
    ) -> tuple[str, Envelope]:
        route = self._routing.get_route_by_connector_id(connector_id)

        # signal-bridge already filters to 1:1 text messages and emits them as
        # {"type":"message","source_uuid":..,"source_name":..,"timestamp":..,"message":..}.
        # We re-check defensively and reject anything else.
        if raw_data.get("type") != "message":
            raise WrongUpdateTypeError
        source_uuid = raw_data.get("source_uuid")
        text = str(raw_data.get("message") or "").strip()
        timestamp = raw_data.get("timestamp")
        if not source_uuid or not text or timestamp is None:
            raise WrongUpdateTypeError

        # The bridge's message timestamp uniquely identifies a message from a
        # given sender, so it is the natural idempotency anchor.
        message_id = str(timestamp)
        to = "chatwoot"

        sender_info = SenderInfo(
            # `source_uuid` is the sender's ACI — a valid send recipient, so it
            # doubles as the reply address.
            external_id=str(source_uuid),
            name=raw_data.get("source_name") or str(source_uuid),
            nickname=str(source_uuid),
        )

        idempotency_key = self.build_idempotency_key(
            direction=f"{channel}->{to}",
            connector_id=route["connector_id"],
            external_id=sender_info["external_id"],
            message_id=message_id,
            # Signal has no platform-issued token; the linked account number
            # stands in as the per-connector fingerprint.
            number_suffix=route["number"][-5:],
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
        # The identifier Chatwoot stores is the Signal source UUID; the bridge
        # accepts it directly as a send recipient.
        recipient = raw_data["conversation"]["meta"]["sender"]["identifier"]
        sender_info = SenderInfo(external_id=recipient)
        message_id = str(raw_data["conversation"]["messages"][0]["id"])
        from_ = "chatwoot"

        idempotency_key = self.build_idempotency_key(
            direction=f"{from_}->{channel}",
            connector_id=route["connector_id"],
            external_id=sender_info["external_id"],
            message_id=message_id,
            number_suffix=route["number"][-5:],
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
