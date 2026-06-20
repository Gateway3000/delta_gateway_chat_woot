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
        envelope_data = raw_data.get("envelope") or {}
        data_message = self._get_one_to_one_text_message(envelope_data)

        sender_info = self._parse_sender_info(envelope_data)
        text = str(data_message.get("message") or "")
        # The dataMessage timestamp uniquely identifies a message from a
        # given sender, so it is the natural idempotency anchor (there is
        # no separate message id in Signal envelopes).
        message_id = str(data_message["timestamp"])
        to = "chatwoot"

        idempotency_key = self.build_idempotency_key(
            direction=f"{channel}->{to}",
            connector_id=route["connector_id"],
            external_id=sender_info["external_id"],
            message_id=message_id,
            # Signal has no platform-issued token; the registered account
            # number stands in as the per-connector fingerprint.
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
        # The identifier Chatwoot stores is the Signal `source` (a UUID or
        # phone number); signal-cli accepts either as a send recipient.
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

    @staticmethod
    def _get_one_to_one_text_message(envelope_data: dict[str, Any]) -> dict[str, Any]:
        """Return the dataMessage iff this is a 1:1 *text* message.

        Signal's receive stream mixes many envelope kinds — `syncMessage`
        (our own activity echoed back), `receiptMessage`, `typingMessage`,
        plus group messages and attachment-only / empty data messages. We
        only forward direct text, so everything else is rejected as a
        WrongUpdateTypeError (the same signal the other channels raise for
        non-actionable updates).
        """
        data_message = envelope_data.get("dataMessage")
        if not isinstance(data_message, dict):
            raise WrongUpdateTypeError
        # Group messages carry a groupInfo block; skip them (1:1 only).
        if data_message.get("groupInfo"):
            raise WrongUpdateTypeError
        if not (data_message.get("message") or "").strip():
            raise WrongUpdateTypeError
        if data_message.get("timestamp") is None:
            raise WrongUpdateTypeError
        return data_message

    @staticmethod
    def _parse_sender_info(envelope_data: dict[str, Any]) -> SenderInfo:
        source = envelope_data.get("source")
        if not source:
            raise WrongUpdateTypeError
        return SenderInfo(
            # `source` is the sender's UUID or number — both are valid
            # send recipients, so it doubles as the reply address.
            external_id=str(source),
            name=envelope_data.get("sourceName") or str(source),
            nickname=envelope_data.get("sourceNumber") or str(source),
        )
