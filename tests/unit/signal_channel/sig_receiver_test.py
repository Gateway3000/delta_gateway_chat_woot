from unittest.mock import AsyncMock, Mock

import pytest

import src.multichannel_gateway.app.wiring as wiring
from channels.signal_channel.sig_receiver import SignalReceiver
from channels.signal_channel.sig_routing import SignalRouting
from channels.signal_channel.plugin_settings import SignalSettings
from src.multichannel_gateway.core import (
    IdempotencyKeyAlreadyProcessedError,
    TransientError,
    WrongUpdateTypeError,
)


@pytest.fixture
def receiver(routing: SignalRouting, settings: SignalSettings) -> SignalReceiver:
    return SignalReceiver(Mock(), routing, settings)


@pytest.fixture
def patched_orchestrator(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    orchestrator = Mock()
    orchestrator.process = AsyncMock()
    monkeypatch.setattr(wiring, "channel_to_chatwoot_orchestrator", orchestrator)
    return orchestrator.process


@pytest.mark.asyncio
class TestSignalReceiverDispatch:
    async def test_dispatch_injects_channel_and_connector(
        self, receiver: SignalReceiver, patched_orchestrator: AsyncMock
    ) -> None:
        item = {"envelope": {"source": "uuid", "dataMessage": {"message": "Hi"}}}

        await receiver._dispatch("sig1", item)

        patched_orchestrator.assert_awaited_once()
        channel_arg, item_arg = patched_orchestrator.await_args.args
        assert channel_arg == "signal"
        assert item_arg["channel"] == "signal"
        assert item_arg["connector_id"] == "sig1"

    @pytest.mark.parametrize(
        "error",
        [WrongUpdateTypeError(), IdempotencyKeyAlreadyProcessedError("dup")],
    )
    async def test_dispatch_swallows_skippable_errors(
        self,
        receiver: SignalReceiver,
        patched_orchestrator: AsyncMock,
        error: Exception,
    ) -> None:
        patched_orchestrator.side_effect = error
        # Must not raise — these just mean "skip this envelope".
        await receiver._dispatch("sig1", {"envelope": {}})

    async def test_dispatch_does_not_raise_on_transient(
        self, receiver: SignalReceiver, patched_orchestrator: AsyncMock
    ) -> None:
        patched_orchestrator.side_effect = TransientError("temporary")
        # The message was already consumed from signal-cli; dropping it must
        # not crash the poll loop.
        await receiver._dispatch("sig1", {"envelope": {}})
