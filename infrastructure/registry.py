from importlib.metadata import entry_points

from core.interfaces.gateway import IGateway


class GatewayRegistry:
    """Registry for managing communication channel gateways.

    This class allows registering, discovering, and retrieving gateways
    by their channel type.
    """

    def __init__(self) -> None:
        self._gateways: dict[str, IGateway] = {}

    def register_gateway(self, gateway: IGateway) -> None:
        """Registers a built-in gateway."""
        self._gateways[gateway.channel] = gateway

    def discover_gateways(self, group: str) -> None:
        """Automatically discovers gateways using entry points."""
        eps = entry_points().select(group=group)
        for ep in eps:  # ep: EntryPoint
            gateway = ep.load()
            self._gateways[gateway.channel] = gateway

    def get_gateway(self, channel: str) -> IGateway:
        """Retrieves a gateway by its channel type."""
        if channel not in self._gateways:
            raise ValueError(f"Gateway for channel '{channel}' not found")
        return self._gateways[channel]
