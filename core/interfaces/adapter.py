from abc import ABC, abstractmethod
from typing import Mapping, Any

from infrastructure.pydantic_models import Envelope


class IAdapter(ABC):
    """Interface for a communication channel adapter."""

    @abstractmethod
    def idempotency_key(self, raw: Mapping[str, Any], route: Mapping[str, str]) -> str:
        """Generates an idempotency key for deduplicating Telegram messages.

        The key is derived from the connector ID, sender ID, and message ID,
        ensuring that each unique message can be processed only once.
        """

    @abstractmethod
    def normalize_inbound(
        self,
        raw: Mapping[str, Any],
        route: Mapping[str, str],
        idempotency_key: str,
        channel: str,
    ) -> Envelope:
        """Normalizes an inbound Telegram message into a standard `Envelope` object.

        This method extracts and converts key fields from the raw Telegram update
        into the internal `Envelope` representation expected by the processing pipeline.
        """
