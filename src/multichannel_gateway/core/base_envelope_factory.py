from hashlib import sha1
from typing import Any


class BaseEnvelopeFactory:
    """Base class for envelope factories with unified idempotency key generation."""

    @staticmethod
    def _build_idempotency_key(
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
