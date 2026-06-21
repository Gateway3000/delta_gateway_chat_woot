from datetime import datetime
from typing import Any

from channels.session_channel.session_routing import SessionRouting
from channels.session_channel.plugin_settings import BOT_SOURCE
from src import Envelope, SenderInfo
from src.multichannel_gateway import WrongUpdateTypeError
from src.multichannel_gateway.core.interfaces.envelope_factory import IEnvelopeFactory


class SelfSourcedMessageError(WrongUpdateTypeError):
    """Raised when an inbound payload is actually our own reply looping back in."""


class SessionEnvelopeFactory(IEnvelopeFactory):
    def __init__(self, routing: SessionRouting) -> None:
        self._routing = routing

    def parse_channel_request(
        self, raw_data: dict[str, Any], connector_id: str, channel: str
    ) -> tuple[str, Envelope]:
        # Replies sent out via this same channel get echoed back in as
        # inbound webhook calls; payloads carrying our own source tag must
        # be dropped here so we don't recurse forever.
        # if raw_data.get("source") == BOT_SOURCE:
        #     raise SelfSourcedMessageError("Ignoring self-sourced session message")

        route = self._routing.get_route_by_connector_id(connector_id)
        sender_info = self._parse_sender_info(raw_data)
        text = self._get_message_text(raw_data)
        message_id = self._build_message_id(raw_data)
        to = "chatwoot"
        idempotency_key = self.build_idempotency_key(
            direction=f"{channel}->{to}",
            connector_id=route["connector_id"],
            external_id=sender_info["external_id"],
            message_id=message_id,
            bot_token_suffix=route["webhook_url"][-5:],
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
        identifier = raw_data["conversation"]["meta"]["sender"]["identifier"]
        sender_info = SenderInfo(
            external_id=identifier,
        )
        message_id = str(raw_data["conversation"]["messages"][0]["id"])
        from_ = "chatwoot"
        idempotency_key = self.build_idempotency_key(
            direction=f"{from_}->{channel}",
            connector_id=route["connector_id"],
            external_id=sender_info["external_id"],
            message_id=message_id,
            bot_token_suffix=route["webhook_url"][-5:],
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
    def _get_message_text(raw_data: dict[str, Any]) -> str:
        return str(raw_data.get("text", ""))

    @staticmethod
    def _parse_sender_info(raw_data: dict[str, Any]) -> SenderInfo:
        try:
            sender = raw_data["sender"]
        except KeyError as e:
            raise WrongUpdateTypeError from e
        return SenderInfo(
            external_id=sender,
            name=sender,
            nickname=sender,
        )

    @staticmethod
    def _build_message_id(raw_data: dict[str, Any]) -> str:
        if "messageId" in raw_data:
            return str(raw_data["messageId"])
        sender = str(raw_data.get("sender", ""))
        text = str(raw_data.get("text", ""))
        return f"{sender}:{hash(text) & 0xFFFFFFFF}"
