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

    def discover_channels(
        self, group: str, channel_names: list[str] | None = None
    ) -> None:
        """Automatically discovers channels using entry points.

        Args:
            group: Entry point group name.
            channel_names: Optional list of channel names to load (case-insensitive).
                          If empty or None, all discovered channels are loaded.
        """
        eps = entry_points().select(group=group)

        target_names = (
            {name.lower() for name in channel_names} if channel_names else None
        )

        discovered = 0
        available = []
        for ep in eps:
            available.append(ep.name)
            channel = ep.load()
            entry_point_names = {
                ep.name.lower(),
                getattr(channel, "channel", "").lower(),
            }
            if target_names and entry_point_names.isdisjoint(target_names):
                continue
            if channel.channel in self._channels:
                logger.warning(
                    "Replacing already registered channel from entry point",
                    channel=channel.channel,
                    entry_point=ep.name,
                )
            self._channels[channel.channel] = channel
            if ep.name != channel.channel:
                self._channels[ep.name] = channel
            discovered += 1

        if target_names:
            if missing := target_names - {name.lower() for name in self._channels}:
                raise RuntimeError(
                    f"Channels not found: {missing}. Available: {available}"
                )

        if discovered == 0:
            if target_names:
                raise RuntimeError(
                    f"No channels matched {channel_names}. Available: {available}"
                )
            raise RuntimeError(
                f"No channels discovered for entry-point group '{group}'"
            )

        logger.info(
            "Discovered channels",
            channels=list(self._channels.keys()),
            total=discovered,
        )

    def get_channel(self, channel: str) -> IChannel:
        """Retrieves a channel by its channel type."""
        if channel not in self._channels:
            raise ValueError(f"Channel '{channel}' not found")
        return self._channels[channel]

    def _unique_channels(self) -> list[IChannel]:
        return list({id(channel): channel for channel in self._channels.values()}.values())

    @property
    def channel_names(self) -> list[str]:
        """Names of all registered channels."""
        return list(self._channels.keys())

    async def on_startup(self) -> None:
        """Performs startup tasks for all registered channels during FastAPI lifespan.

        This method is typically used to prepare all communication channels before the
        FastAPI application starts.
        """
        tasks = []
        for channel in self._unique_channels():
            startup_task = asyncio.create_task(channel.on_startup())
            tasks.append(startup_task)
            logger.info(f'Initializing channel "{channel.channel}"...')
        await asyncio.gather(*tasks)

    async def on_shutdown(self) -> None:
        """Performs shutdown tasks for all registered channels during FastAPI lifespan.

        This method is typically used to gracefully close all communication channels
        when the FastAPI application is shutting down.
        """
        tasks = []
        for channel in self._unique_channels():
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
        for channel in self._unique_channels():
            prefork_task = asyncio.create_task(channel.on_prefork())
            tasks.append(prefork_task)
            logger.debug(f'Executing prefork for channel "{channel.channel}"...')
        await asyncio.gather(*tasks)
