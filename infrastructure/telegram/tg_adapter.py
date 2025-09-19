import time
from typing import Mapping, Any

from core.interfaces.adapter import IAdapter
from infrastructure.pydantic_models import Envelope


class TelegramAdapter(IAdapter):
    def idempotency_key(self, raw: Mapping[str, Any], route: Mapping[str, str]) -> str:
        return f"tg:{route['connector_id']}:{raw['from']['id']}:{raw['message_id']}"

    def normalize_inbound(
        self,
        raw: Mapping[str, Any],
        route: Mapping[str, str],
        idempotency_key: str,
        channel: str,
    ) -> Envelope:
        if not raw:
            raise ValueError("Unsupported update type")
        return Envelope(
            id=idempotency_key,
            channel=channel,
            connector_id=route["connector_id"],
            cw_account_id=route["cw_account_id"],
            sender={"external_id": raw["from"]["id"]},
            payload={"text": raw["text"] or ""},
            ts=time.time(),
        )
