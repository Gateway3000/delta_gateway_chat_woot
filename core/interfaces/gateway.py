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
    async def send_to_user(
        self, message: dict[str, Any], limiter: Any = None
    ) -> DeliveryResult:
        """Sends a message to the end user via the specified channel."""

    @abstractmethod
    async def process_inbound(
        self,
        raw_data: dict[str, Any],
        connector_id: str,
    ) -> None:
        """Processes an inbound message received from an external channel."""

    @abstractmethod
    async def process_outbound(
        self, raw_data: dict[str, Any], cw_account_id: str
    ) -> None:
        """Processes an outbound message originating from Chatwoot."""

    @abstractmethod
    async def on_startup(self) -> None:
        """Called when the application starts up."""

    @abstractmethod
    async def on_shutdown(self) -> None:
        """Called when the application shuts down."""
