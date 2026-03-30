from datetime import datetime
from typing import Mapping, Any

from src import Envelope, SenderInfo
from src.multichannel_gateway.app.chatwoot_attachments import (
    extract_chatwoot_attachments,
)
from telegram.tg_attachments import extract_telegram_attachments
from telegram.tg_routing import TelegramRouting


class TelegramAdapter:
    def __init__(self, routing: TelegramRouting) -> None:
        self._routing = routing

    @staticmethod
    def idempotency_key(
        sender_id: str, msg_id: str, route: Mapping[str, str], from_: str, to: str
    ) -> str:
        return f"{from_}->{to}:{route['connector_id']}:{route['bot_token'][-5:]}:{sender_id}:{msg_id}"

    def parse_channel_request(
        self, raw_data: dict[str, Any], connector_id: str, channel: str
    ) -> tuple[str, Envelope]:
        route = self._routing.get_route_by_connector_id(connector_id)
        sender_info = self._parse_sender_info(raw_data=raw_data)
        text = raw_data.get("message", {}).get("text") or raw_data.get(
            "message", {}
        ).get("caption", "")
        attachments = extract_telegram_attachments(raw_data)
        envelope = Envelope(
            idem_key="idempotency_key",
            channel=channel,
            from_=channel,
            to="chatwoot",
            connector_id=route["connector_id"],
            cw_inbox_id=route["cw_inbox_id"],
            cw_account_id=route["cw_account_id"],
            message_id=str(raw_data["message"]["message_id"]),
            sender=sender_info,
            payload={"text": text, "attachments": attachments, "raw_data": raw_data},
            ts=float(datetime.now().timestamp()),
        )
        idempotency_key = self.idempotency_key(
            envelope.sender["external_id"],
            envelope.message_id,
            route,
            envelope.from_,
            envelope.to,
        )
        envelope.idem_key = idempotency_key
        return idempotency_key, envelope

    def parse_chatwoot_request(
        self, raw_data: dict[str, Any], cw_account_id: str, channel: str
    ) -> tuple[str, Envelope]:
        route = self._routing.get_route_by_inbox_id(str(raw_data["inbox"]["id"]))
        attachments = extract_chatwoot_attachments(raw_data)
        sender_info = SenderInfo(
            external_id=raw_data["conversation"]["meta"]["sender"]["identifier"],
        )
        envelope = Envelope(
            idem_key="",
            channel=channel,
            from_="chatwoot",
            to=channel,
            connector_id=route["connector_id"],
            cw_inbox_id=str(raw_data["inbox"]["id"]),
            cw_account_id=cw_account_id,
            message_id=str(raw_data["conversation"]["messages"][0]["id"]),
            sender=sender_info,
            payload={"text": raw_data.get("content", ""), "attachments": attachments},
            ts=float(datetime.now().timestamp()),
        )
        idempotency_key = self.idempotency_key(
            envelope.sender["external_id"],
            envelope.message_id,
            route,
            envelope.from_,
            envelope.to,
        )
        envelope.idem_key = idempotency_key
        return idempotency_key, envelope

    @staticmethod
    def _parse_sender_info(raw_data: dict[str, Any]) -> SenderInfo:
        message_from_info = raw_data["message"]["from"]
        full_name_formed = f"{message_from_info.get('first_name', ' ')} {message_from_info.get('last_name', ' ')}".strip()

        return SenderInfo(
            external_id=message_from_info["id"],
            name=full_name_formed,
            nickname=message_from_info.get("username", ""),
        )
