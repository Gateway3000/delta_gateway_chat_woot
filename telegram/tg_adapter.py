from datetime import datetime
from typing import Mapping, Any

from src import Envelope
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
        envelope = Envelope(
            idem_key="idempotency_key",
            channel=channel,
            from_=channel,
            to="chatwoot",
            connector_id=route["connector_id"],
            cw_inbox_id=route["cw_inbox_id"],
            cw_account_id=route["cw_account_id"],
            message_id=str(raw_data["message"]["message_id"]),
            sender={"external_id": raw_data["message"]["from"]["id"]},
            payload={"text": raw_data["message"]["text"], "raw_data": raw_data},
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
        envelope = Envelope(
            idem_key="",
            channel=channel,
            from_="chatwoot",
            to=channel,
            connector_id=route["connector_id"],
            cw_inbox_id=str(raw_data["inbox"]["id"]),
            cw_account_id=cw_account_id,
            message_id=str(raw_data["conversation"]["messages"][0]["id"]),
            sender={
                "external_id": raw_data["conversation"]["meta"]["sender"]["identifier"]
            },
            payload={"text": raw_data["content"]},
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
