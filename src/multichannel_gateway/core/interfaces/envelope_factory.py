from abc import ABC, abstractmethod
from hashlib import sha1
from typing import Any

from src.multichannel_gateway.core import Envelope


class IEnvelopeFactory(ABC):
    """Interface for envelope factories with unified idempotency key generation."""

    @abstractmethod
    def parse_channel_request(
        self, raw_data: dict[str, Any], connector_id: str, channel: str
    ) -> tuple[str, Envelope]:
        """Parses a channel request into an idempotency key and Envelope."""

    @abstractmethod
    def parse_chatwoot_request(
        self, raw_data: dict[str, Any], cw_account_id: str, channel: str
    ) -> tuple[str, Envelope]:
        """Parses a Chatwoot request into an idempotency key and Envelope."""

    @staticmethod
    def build_idempotency_key(
        direction: str,
        connector_id: str,
        external_id: str,
        message_id: str,
        **extra: str,
    ) -> str:
        if not external_id:
            raise ValueError("external_id is required for idempotency key")
        if not message_id:
            raise ValueError("message_id is required for idempotency key")

        def _hash(value: Any) -> str:
            return sha1(str(value).encode("utf-8")).hexdigest()[:12]

        sorted_extra = dict(sorted(extra.items()))
        extra_hash = (
            _hash(":".join(f"{k}={v}" for k, v in sorted_extra.items()))
            if extra
            else "0" * 12
        )

        return f"{direction}:{connector_id}:{extra_hash}:{_hash(external_id)}:{_hash(message_id)}"

    @staticmethod
    def _add_channel_prefix(raw_id: str | int, channel: str) -> str:
        return f"{channel}_{raw_id}"

    @staticmethod
    def _strip_channel_prefix(identifier: str, channel: str) -> str:
        prefix = f"{channel}_"
        if isinstance(identifier, str) and identifier.startswith(prefix):
            return identifier[len(prefix) :]
        return identifier
