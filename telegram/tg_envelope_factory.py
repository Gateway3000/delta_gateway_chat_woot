from datetime import datetime
from typing import Any

from src import Envelope, SenderInfo
from src.multichannel_gateway.app.chatwoot_attachments import (
    extract_chatwoot_attachments,
)
from src.multichannel_gateway.core.interfaces.envelope_factory import IEnvelopeFactory
from telegram.tg_attachments import extract_telegram_attachments
from telegram.tg_routing import TelegramRouting


class TelegramEnvelopeFactory(IEnvelopeFactory):
    def __init__(self, routing: TelegramRouting) -> None:
        self._routing = routing

    def parse_channel_request(
        self, raw_data: dict[str, Any], connector_id: str, channel: str
    ) -> tuple[str, Envelope]:
        route = self._routing.get_route_by_connector_id(connector_id)
        sender_info = self._parse_sender_info(raw_data)
        text = self._get_message_text(raw_data)
        attachments = extract_telegram_attachments(raw_data)

        message_id = str(raw_data["message"]["message_id"])
        to = "chatwoot"

        idempotency_key = self.build_idempotency_key(
            direction=f"{channel}->{to}",
            connector_id=route["connector_id"],
            external_id=sender_info["external_id"],
            message_id=message_id,
            bot_token_suffix=route["bot_token"][-5:],
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
            payload={"text": text, "attachments": attachments, "raw_data": raw_data},
            ts=float(datetime.now().timestamp()),
        )

        return envelope.idem_key, envelope

    def parse_chatwoot_request(
        self, raw_data: dict[str, Any], cw_account_id: str, channel: str
    ) -> tuple[str, Envelope]:
        route = self._routing.get_route_by_inbox_id(str(raw_data["inbox"]["id"]))
        attachments = extract_chatwoot_attachments(raw_data)
        sender_info = SenderInfo(
            external_id=raw_data["conversation"]["meta"]["sender"]["identifier"],
        )

        message_id = str(raw_data["conversation"]["messages"][0]["id"])
        from_ = "chatwoot"

        idempotency_key = self.build_idempotency_key(
            direction=f"{from_}->{channel}",
            connector_id=route["connector_id"],
            external_id=sender_info["external_id"],
            message_id=message_id,
            bot_token_suffix=route["bot_token"][-5:],
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
            payload={"text": raw_data.get("content", ""), "attachments": attachments},
            ts=float(datetime.now().timestamp()),
        )

        return envelope.idem_key, envelope

    @staticmethod
    def _get_message_text(raw_data: dict[str, Any]) -> Any:
        return raw_data.get("message", {}).get("text") or raw_data.get(
            "message", {}
        ).get("caption", "")

    @staticmethod
    def _parse_sender_info(raw_data: dict[str, Any]) -> SenderInfo:
        message_from_info = raw_data["message"]["from"]
        full_name_formed = f"{message_from_info.get('first_name', ' ')} {message_from_info.get('last_name', ' ')}".strip()

        return SenderInfo(
            external_id=message_from_info["id"],
            name=full_name_formed,
            nickname=message_from_info.get("username", ""),
        )
