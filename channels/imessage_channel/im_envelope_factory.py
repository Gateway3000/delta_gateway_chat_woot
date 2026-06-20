from datetime import datetime
from typing import Any

from channels.imessage_channel.im_attachments import extract_imessage_attachments
from channels.imessage_channel.im_routing import IMessageRouting
from src import Envelope, SenderInfo
from src.multichannel_gateway import WrongUpdateTypeError
from src.multichannel_gateway.app.chatwoot_attachments import (
    extract_chatwoot_attachments,
)
from src.multichannel_gateway.core.interfaces.envelope_factory import IEnvelopeFactory


class IMessageEnvelopeFactory(IEnvelopeFactory):
    def __init__(self, routing: IMessageRouting) -> None:
        self._routing = routing

    def parse_channel_request(
        self, raw_data: dict[str, Any], connector_id: str, channel: str
    ) -> tuple[str, Envelope]:
        route = self._routing.get_route_by_connector_id(connector_id)
        sender_info = self._parse_sender_info(raw_data)
        chat_guid = self._get_chat_guid(raw_data)
        text = self._get_message_text(raw_data)
        attachments = extract_imessage_attachments(raw_data)
        message_id = str(raw_data["data"]["guid"])
        to = "chatwoot"

        idempotency_key = self.build_idempotency_key(
            direction=f"{channel}->{to}",
            connector_id=route["connector_id"],
            external_id=sender_info["external_id"],
            message_id=message_id,
            # BlueBubbles has no platform-issued token to fingerprint the
            # connector by, so the server's own GUID/chat identity stands
            # in for the "bot_token_suffix" role Telegram's key uses.
            bot_token_suffix=route["server_password"][-5:],
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
            payload={
                "text": text,
                "attachments": attachments,
                "chat_guid": chat_guid,
                "raw_data": raw_data,
            },
            ts=float(datetime.now().timestamp()),
        )
        return envelope.idem_key, envelope

    def parse_chatwoot_request(
        self, raw_data: dict[str, Any], cw_account_id: str, channel: str
    ) -> tuple[str, Envelope]:
        route = self._routing.get_route_by_inbox_id(str(raw_data["inbox"]["id"]))
        attachments = extract_chatwoot_attachments(raw_data)
        # The "identifier" Chatwoot stores for this channel must be the
        # chat_guid (e.g. "iMessage;-;+15551234567"), since that's what
        # BlueBubbles needs to send a reply — a bare phone number/email
        # alone is not enough to address a specific chat (group chats in
        # particular have no single-handle identity).
        chat_guid = raw_data["conversation"]["meta"]["sender"]["identifier"]
        sender_info = SenderInfo(
            external_id=chat_guid,
        )
        message_id = str(raw_data["conversation"]["messages"][0]["id"])
        from_ = "chatwoot"

        idempotency_key = self.build_idempotency_key(
            direction=f"{from_}->{channel}",
            connector_id=route["connector_id"],
            external_id=sender_info["external_id"],
            message_id=message_id,
            bot_token_suffix=route["server_password"][-5:],
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
            payload={
                "text": raw_data.get("content", ""),
                "attachments": attachments,
                "chat_guid": chat_guid,
            },
            ts=float(datetime.now().timestamp()),
        )
        return envelope.idem_key, envelope

    @staticmethod
    def _get_message_text(raw_data: dict[str, Any]) -> Any:
        return raw_data.get("data", {}).get("text") or ""

    @staticmethod
    def _get_chat_guid(raw_data: dict[str, Any]) -> str:
        chats = raw_data.get("data", {}).get("chats") or []
        if not chats:
            raise WrongUpdateTypeError
        return str(chats[0]["guid"])

    @staticmethod
    def _parse_sender_info(raw_data: dict[str, Any]) -> SenderInfo:
        try:
            message_data = raw_data["data"]
            # Ignore our own outgoing messages echoed back by the webhook —
            # BlueBubbles fires "new-message" for both directions.
            if message_data.get("isFromMe"):
                raise WrongUpdateTypeError
            handle = message_data["handle"]
        except KeyError as e:
            raise WrongUpdateTypeError from e

        address = handle.get("address", "")
        return SenderInfo(
            # iMessage has no numeric user ID — the phone number/email
            # *is* the identity, and routing reuses chat_guid (not bare
            # address) to address replies correctly, including group chats.
            external_id=IMessageEnvelopeFactory._get_chat_guid(raw_data),
            name=address,
            nickname=address,
        )
