from typing import cast
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from channels.signal_channel.sig_bot_manager import SignalAPIError, SignalBotManager
from channels.signal_channel.sig_transport import SignalTransport
from src.multichannel_gateway.core.exceptions import (
    FatalError,
    RateLimitError,
    TransientError,
)


def _build_bot_manager(client: Mock) -> SignalBotManager:
    bot_manager = Mock(spec=SignalBotManager)
    bot_manager.get_client_by_connector_id.return_value = client
    return cast(SignalBotManager, bot_manager)


def _build_message(text: str = "Hello back") -> dict[str, object]:
    return {
        "idem_key": "chatwoot->signal:sig1:x:y:z",
        "channel": "signal",
        "from_": "chatwoot",
        "to": "signal",
        "connector_id": "sig1",
        "cw_inbox_id": "11",
        "message_id": "555",
        "cw_account_id": "1",
        "sender": {"external_id": "2647ff35-bb65-4459-90d8-c5c832c04d08"},
        "payload": {"text": text},
        "ts": 1.0,
    }


async def _noop_limiter(_: float) -> None:
    return None


@pytest.mark.asyncio
class TestSignalTransport:
    async def test_sends_text_to_recipient(self) -> None:
        client = Mock()
        client.send_text = AsyncMock(return_value={"timestamp": 1781965272850})
        transport = SignalTransport(_build_bot_manager(client))

        result = await transport.send_to_signal_user(
            _build_message(), limiter=_noop_limiter
        )

        client.send_text.assert_awaited_once_with(
            "2647ff35-bb65-4459-90d8-c5c832c04d08", "Hello back"
        )
        assert result.ok is True
        assert result.external_id == "1781965272850"

    async def test_empty_text_is_fatal(self) -> None:
        client = Mock()
        client.send_text = AsyncMock()
        transport = SignalTransport(_build_bot_manager(client))

        with pytest.raises(FatalError):
            await transport.send_to_signal_user(
                _build_message(text="   "), limiter=_noop_limiter
            )
        client.send_text.assert_not_awaited()

    async def test_network_error_is_transient(self) -> None:
        client = Mock()
        client.send_text = AsyncMock(side_effect=httpx.ConnectError("boom"))
        transport = SignalTransport(_build_bot_manager(client))

        with pytest.raises(TransientError):
            await transport.send_to_signal_user(
                _build_message(), limiter=_noop_limiter
            )

    async def test_rate_limit_maps_to_rate_limit_error(self) -> None:
        client = Mock()
        client.send_text = AsyncMock(
            side_effect=SignalAPIError(status=429, message="slow down")
        )
        transport = SignalTransport(_build_bot_manager(client))

        with pytest.raises(RateLimitError):
            await transport.send_to_signal_user(
                _build_message(), limiter=_noop_limiter
            )

    async def test_other_api_error_is_fatal(self) -> None:
        client = Mock()
        client.send_text = AsyncMock(
            side_effect=SignalAPIError(status=400, message="bad request")
        )
        transport = SignalTransport(_build_bot_manager(client))

        with pytest.raises(FatalError):
            await transport.send_to_signal_user(
                _build_message(), limiter=_noop_limiter
            )
