from abc import ABC, abstractmethod
from typing import Any, Literal

from src.multichannel_gateway.core import ChannelDeliveryResult, Envelope


class IChannel(ABC):
    """Interface for a channel Gateway.

    This represents a high-level API for interacting with communication channels.
    All interactions with subsystems should be performed through the Gateway methods,
    not by calling subsystem methods directly.
    """

    channel: Literal["telegram", "email", "signal", "whatsapp", "telephony", "viber"]

    async def on_prefork(self) -> None:
        """Performs actions before the process fork."""
        pass

    @abstractmethod
    def get_route_by_connector_id(self, connector_id: str) -> dict[str, str]:
        """Retrieves the route information associated with a given connector ID."""

    @abstractmethod
    async def send_to_user(
        self, message: dict[str, Any], limiter: Any = None
    ) -> ChannelDeliveryResult:
        """Sends a message to the end user via the specified channel."""

    @abstractmethod
    async def build_channel_message(
        self, raw_data: dict[str, Any]
    ) -> tuple[str, Envelope]:
        """Builds a Channel -> Chatwoot message from raw channel payload."""

    @abstractmethod
    async def publish_channel_message(
        self,
        idempotency_key: str,
        envelope: Envelope,
        raw_data: dict[str, Any],
    ) -> None:
        """Publishes a prepared Channel -> Chatwoot message for delivery."""

    @abstractmethod
    async def publish_chatwoot_message(
        self, raw_data: dict[str, Any], cw_account_id: str
    ) -> None:
        """Processes a Chatwoot -> Channel message."""

    async def on_startup(self) -> None:
        """Called when the application starts up."""
        pass

    async def on_shutdown(self) -> None:
        """Called when the application shuts down."""
        pass
