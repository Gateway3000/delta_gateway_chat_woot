import asyncio
from importlib.metadata import entry_points

import structlog

from src.multichannel_gateway.core.interfaces import IChannel

logger = structlog.get_logger(__name__)


class ChannelRegistry:
    """Registry for managing communication channels.

    This class allows registering, discovering, and retrieving channels
    by their channel type.
    """

    def __init__(self) -> None:
        self._channels: dict[str, IChannel] = {}

    def discover_channels(self, group: str) -> None:
        """Automatically discovers channels using entry points."""
        eps = entry_points().select(group=group)

        discovered = 0
        for ep in eps:  # ep: EntryPoint
            channel = ep.load()
            logger.info(f'Found channel: "{ep.name}"')
            if channel.channel in self._channels:
                logger.warning(
                    "Replacing already registered channel from entry point",
                    channel=channel.channel,
                    entry_point=ep.name,
                )
            self._channels[channel.channel] = channel
            discovered += 1

        if discovered == 0:
            raise RuntimeError(
                f"No channels discovered for entry-point group '{group}'"
            )

    def get_channel(self, channel: str) -> IChannel:
        """Retrieves a channel by its channel type."""
        if channel not in self._channels:
            raise ValueError(f"Channel '{channel}' not found")
        return self._channels[channel]

    async def on_startup(self) -> None:
        """Performs startup tasks for all registered channels during FastAPI lifespan.

        This method is typically used to prepare all communication channels before the
        FastAPI application starts.
        """
        tasks = []
        for channel in self._channels.values():
            startup_task = asyncio.create_task(channel.on_startup())
            tasks.append(startup_task)
            logger.debug(f'Initializing channel "{channel.channel}"...')
        await asyncio.gather(*tasks)

    async def on_shutdown(self) -> None:
        """Performs shutdown tasks for all registered channels during FastAPI lifespan.

        This method is typically used to gracefully close all communication channels
        when the FastAPI application is shutting down.
        """
        tasks = []
        for channel in self._channels.values():
            shutdown_task = asyncio.create_task(channel.on_shutdown())
            tasks.append(shutdown_task)
            logger.info(f'Initiating shutdown for channel "{channel.channel}"...')
        await asyncio.gather(*tasks)

    async def on_prefork(self) -> None:
        """Performs tasks before forking processes.

        This method is typically called during the app preparation stage, just before
        launching the FastAPI app, ensuring all communication channels are properly
        prepared for multiprocess execution.
        """
        tasks = []
        for channel in self._channels.values():
            prefork_task = asyncio.create_task(channel.on_prefork())
            tasks.append(prefork_task)
            logger.debug(f'Executing prefork for channel "{channel.channel}"...')
        await asyncio.gather(*tasks)
