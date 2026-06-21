from unittest.mock import AsyncMock, Mock

import pytest
from pytest_mock import MockerFixture

from src.multichannel_gateway.app.config import Settings
from src.multichannel_gateway.infrastructure.registry import ChannelRegistry, logger


class TestChannelRegistryDiscoverChannels:
    GROUP = "multichannel_gateway.channels"
    registry = ChannelRegistry()

    def test_warns_on_replacing_registered_channel(self, mocker: MockerFixture) -> None:
        """Warning when channel.channel is already registered."""

        self.registry._channels["telegram"] = Mock(channel="telegram")
        warn_spy = mocker.patch.object(logger, "warning")
        settings = Settings(channels=["telegram"])

        self.registry.discover_channels(self.GROUP, settings.channels)

        warn_spy.assert_called_once()

    def test_raises_on_missing_targets(self) -> None:
        """target_names missing from registered channels."""

        settings = Settings(channels=["telegram", "nonexistent"])

        with pytest.raises(RuntimeError, match="Channels not found"):
            self.registry.discover_channels(self.GROUP, settings.channels)

    def test_raises_no_match_when_target_already_in_channels(self) -> None:
        """discovered == 0 with target_names all pre-registered."""

        self.registry._channels["nonexistent"] = Mock(channel="nonexistent")
        settings = Settings(channels=["nonexistent"])

        with pytest.raises(RuntimeError, match="No channels matched"):
            self.registry.discover_channels(self.GROUP, settings.channels)

    def test_raises_no_channels_discovered(self) -> None:
        """No entry points found for the group."""

        with pytest.raises(RuntimeError, match="No channels discovered"):
            self.registry.discover_channels("nonexistent.group")


@pytest.mark.asyncio
async def test_channel_aliases_share_one_lifecycle() -> None:
    registry = ChannelRegistry()
    channel = Mock(channel="delta_chat")
    channel.on_startup = AsyncMock()
    registry._channels = {"delta_chat": channel, "deltachat": channel}

    await registry.on_startup()

    channel.on_startup.assert_awaited_once_with()
