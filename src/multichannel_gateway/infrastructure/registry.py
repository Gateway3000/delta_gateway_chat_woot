import asyncio
from importlib.metadata import entry_points

import structlog

from src.multichannel_gateway.core.interfaces import IChannel

logger = structlog.get_logger(__name__)


class GatewayRegistry:
    """Registry for managing communication channel gateways.

    This class allows registering, discovering, and retrieving gateways
    by their channel type.
    """

    def __init__(self) -> None:
        self._gateways: dict[str, IChannel] = {}

    def register_gateway(self, gateway: IChannel) -> None:
        """Registers a built-in gateway."""
        self._gateways[gateway.channel] = gateway

    def discover_gateways(self, group: str) -> None:
        """Automatically discovers gateways using entry points."""
        eps = entry_points().select(group=group)
        for ep in eps:  # ep: EntryPoint
            gateway = ep.load()
            self._gateways[gateway.channel] = gateway

    def get_gateway(self, channel: str) -> IChannel:
        """Retrieves a gateway by its channel type."""
        if channel not in self._gateways:
            raise ValueError(f"Gateway for channel '{channel}' not found")
        return self._gateways[channel]

    async def on_startup(self) -> None:
        """Performs startup tasks for all registered gateways during FastAPI lifespan.

        This method is typically used to prepare all communication channels before the
        FastAPI application starts.
        """
        tasks = []
        for gateway in self._gateways.values():
            startup_task = asyncio.create_task(gateway.on_startup())
            tasks.append(startup_task)
            logger.debug(f'Initializing gateway for channel "{gateway.channel}"...')
        await asyncio.gather(*tasks)

    async def on_shutdown(self) -> None:
        """Performs shutdown tasks for all registered gateways during FastAPI lifespan.

        This method is typically used to gracefully close all communication channels
        when the FastAPI application is shutting down.
        """
        tasks = []
        for gateway in self._gateways.values():
            shutdown_task = asyncio.create_task(gateway.on_shutdown())
            tasks.append(shutdown_task)
            logger.info(
                f'Initiating shutdown for gateway on channel "{gateway.channel}"...'
            )
        await asyncio.gather(*tasks)

    async def on_prefork(self) -> None:
        """Performs tasks before forking processes.

        This method is typically called during the app preparation stage, just before
        launching the FastAPI app, ensuring all communication channels are properly
        prepared for multiprocess execution.
        """
        tasks = []
        for gateway in self._gateways.values():
            prefork_task = asyncio.create_task(gateway.on_prefork())
            tasks.append(prefork_task)
            logger.debug(f'Executing prefork for channel "{gateway.channel}"...')
        await asyncio.gather(*tasks)
