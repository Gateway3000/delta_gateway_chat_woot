import time
from typing import Mapping, Any

from infrastructure.pydantic_models import Envelope


class TelegramAdapter:
    @staticmethod
    def idempotency_key(raw: Mapping[str, Any], route: Mapping[str, str]) -> str:
        return f"tg:{route['connector_id']}:{raw['from']['id']}:{raw['message_id']}"

    @staticmethod
    def normalize_inbound(
        raw: Mapping[str, Any],
        route: Mapping[str, str],
        idempotency_key: str,
        channel: str,
    ) -> Envelope:
        if not raw:
            raise ValueError("Unsupported update type")
        return Envelope(
            idempotency_key=idempotency_key,
            channel=channel,
            connector_id=route["connector_id"],
            cw_account_id=route["cw_account_id"],
            sender={"external_id": raw["from"]["id"]},
            payload={"text": raw.get("text") or ""},
            ts=time.time(),
        )
