from abc import ABC, abstractmethod
from typing import Any, Literal

from infrastructure.pydantic_models import DeliveryResult


class IGateway(ABC):
    """Interface for a channel Gateway.

    This represents a high-level API for interacting with communication channels.
    All interactions with subsystems should be performed through the Gateway methods,
    not by calling subsystem methods directly.
    """

    channel: Literal["telegram", "signal", "whatsapp", "telephony", "viber"]

    @abstractmethod
    def get_route_by_connector_id(self, connector_id: str) -> dict[str, str]:
        """Retrieves the route information associated with a given connector ID."""

    @abstractmethod
    def get_route_by_cw_account_id(self, cw_account_id: str) -> dict[str, str]:
        """Retrieves the route information associated with a given Chatwoot account ID."""

    @abstractmethod
    def get_connector_id(self, cw_account_id: str) -> str:
        """Returns the connector ID corresponding to a Chatwoot account ID."""

    @abstractmethod
    async def send_to_user(
        self, message: dict[str, Any], limiter: Any = None
    ) -> DeliveryResult:
        """Sends a message to the end user via the specified channel."""

    @abstractmethod
    async def process_inbound(
        self, connector_id: str, raw_data: dict[str, Any]
    ) -> None:
        """Processes an inbound message received from an external channel."""

    @abstractmethod
    async def process_outbound(
        self, cw_account_id: str, raw_data: dict[str, Any]
    ) -> None:
        """Processes an outbound message originating from Chatwoot."""
