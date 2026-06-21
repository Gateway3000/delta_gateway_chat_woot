from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest

from channels.simplex_channel.sx_bot_manager import SimplexBotManager, SimplexError
from channels.simplex_channel.sx_transport import SimplexTransport
from src.multichannel_gateway.core.exceptions import FatalError, TransientError


def _build_bot_manager(conn: Mock) -> SimplexBotManager:
    bot_manager = Mock(spec=SimplexBotManager)
    bot_manager.get_client_by_connector_id.return_value = conn
    return cast(SimplexBotManager, bot_manager)


def _build_message(text: str = "Hello back") -> dict[str, object]:
    return {
        "idem_key": "chatwoot->simplex:sx1:x:y:z",
        "channel": "simplex",
        "from_": "chatwoot",
        "to": "simplex",
        "connector_id": "sx1",
        "cw_inbox_id": "5",
        "message_id": "555",
        "cw_account_id": "1",
        "sender": {"external_id": "42"},
        "payload": {"text": text},
        "ts": 1.0,
    }


async def _noop_limiter(_: float) -> None:
    return None


@pytest.mark.asyncio
class TestSimplexTransport:
    async def test_sends_text_to_contact(self) -> None:
        conn = Mock()
        conn.send_text = AsyncMock(
            return_value={
                "type": "newChatItems",
                "chatItems": [{"chatItem": {"meta": {"itemId": 2002}}}],
            }
        )
        transport = SimplexTransport(_build_bot_manager(conn))

        result = await transport.send_to_simplex_user(
            _build_message(), limiter=_noop_limiter
        )

        conn.send_text.assert_awaited_once_with("42", "Hello back")
        assert result.ok is True
        assert result.external_id == "2002"

    async def test_empty_text_is_fatal(self) -> None:
        conn = Mock()
        conn.send_text = AsyncMock()
        transport = SimplexTransport(_build_bot_manager(conn))

        with pytest.raises(FatalError):
            await transport.send_to_simplex_user(
                _build_message(text="   "), limiter=_noop_limiter
            )
        conn.send_text.assert_not_awaited()

    async def test_transient_error_is_transient(self) -> None:
        conn = Mock()
        conn.send_text = AsyncMock(
            side_effect=SimplexError("connection lost", transient=True)
        )
        transport = SimplexTransport(_build_bot_manager(conn))

        with pytest.raises(TransientError):
            await transport.send_to_simplex_user(
                _build_message(), limiter=_noop_limiter
            )

    async def test_permanent_error_is_fatal(self) -> None:
        conn = Mock()
        conn.send_text = AsyncMock(side_effect=SimplexError("bad contact"))
        transport = SimplexTransport(_build_bot_manager(conn))

        with pytest.raises(FatalError):
            await transport.send_to_simplex_user(
                _build_message(), limiter=_noop_limiter
            )
