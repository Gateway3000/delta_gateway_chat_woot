import base64
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest

from channels.signal_channel.sig_bot_manager import SignalBotManager, SignalBridgeError
from channels.signal_channel.sig_transport import SignalTransport
from src.multichannel_gateway.core.exceptions import FatalError, TransientError


def _build_bot_manager(conn: Mock) -> SignalBotManager:
    bot_manager = Mock(spec=SignalBotManager)
    bot_manager.get_client_by_connector_id.return_value = conn
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
        conn = Mock()
        conn.send = AsyncMock(return_value={"ok": True, "timestamp": 1781965272850})
        transport = SignalTransport(_build_bot_manager(conn))

        result = await transport.send_to_signal_user(
            _build_message(), limiter=_noop_limiter
        )

        conn.send.assert_awaited_once_with(
            "2647ff35-bb65-4459-90d8-c5c832c04d08", "Hello back", []
        )
        assert result.ok is True
        assert result.external_id == "1781965272850"

    async def test_empty_text_is_fatal(self) -> None:
        conn = Mock()
        conn.send = AsyncMock()
        transport = SignalTransport(_build_bot_manager(conn))

        with pytest.raises(FatalError):
            await transport.send_to_signal_user(
                _build_message(text="   "), limiter=_noop_limiter
            )
        conn.send.assert_not_awaited()

    async def test_sends_attachment_as_base64(self, monkeypatch) -> None:
        conn = Mock()
        conn.send = AsyncMock(return_value={"ok": True, "timestamp": 1781965272850})
        transport = SignalTransport(_build_bot_manager(conn))

        fetch = AsyncMock(return_value=b"\x89PNG\r\n")
        monkeypatch.setattr(
            SignalTransport, "_fetch_outbound_attachment", staticmethod(fetch)
        )

        message = _build_message(text="see pic")
        message["payload"]["attachments"] = [
            {
                "data_url": "https://cw.example/pic.png",
                "mime_type": "image/png",
                "filename": "pic.png",
            }
        ]

        result = await transport.send_to_signal_user(message, limiter=_noop_limiter)

        fetch.assert_awaited_once_with("https://cw.example/pic.png")
        conn.send.assert_awaited_once_with(
            "2647ff35-bb65-4459-90d8-c5c832c04d08",
            "see pic",
            [
                {
                    "data": base64.b64encode(b"\x89PNG\r\n").decode("ascii"),
                    "content_type": "image/png",
                    "filename": "pic.png",
                }
            ],
        )
        assert result.ok is True

    async def test_attachment_only_send_is_allowed(self, monkeypatch) -> None:
        conn = Mock()
        conn.send = AsyncMock(return_value={"ok": True, "timestamp": 1781965272850})
        transport = SignalTransport(_build_bot_manager(conn))

        monkeypatch.setattr(
            SignalTransport,
            "_fetch_outbound_attachment",
            staticmethod(AsyncMock(return_value=b"data")),
        )

        message = _build_message(text="")
        message["payload"]["attachments"] = [
            {"data_url": "https://cw.example/file.bin"}
        ]

        result = await transport.send_to_signal_user(message, limiter=_noop_limiter)

        assert result.ok is True
        _, sent_text, sent_attachments = conn.send.await_args.args
        assert sent_text == ""
        assert len(sent_attachments) == 1

    async def test_transient_bridge_error_is_transient(self) -> None:
        conn = Mock()
        conn.send = AsyncMock(
            side_effect=SignalBridgeError("connection lost", transient=True)
        )
        transport = SignalTransport(_build_bot_manager(conn))

        with pytest.raises(TransientError):
            await transport.send_to_signal_user(
                _build_message(), limiter=_noop_limiter
            )

    async def test_permanent_bridge_error_is_fatal(self) -> None:
        conn = Mock()
        conn.send = AsyncMock(side_effect=SignalBridgeError("bad recipient"))
        transport = SignalTransport(_build_bot_manager(conn))

        with pytest.raises(FatalError):
            await transport.send_to_signal_user(
                _build_message(), limiter=_noop_limiter
            )

    async def test_send_result_not_ok_is_fatal(self) -> None:
        conn = Mock()
        conn.send = AsyncMock(return_value={"ok": False, "error": "unregistered user"})
        transport = SignalTransport(_build_bot_manager(conn))

        with pytest.raises(FatalError):
            await transport.send_to_signal_user(
                _build_message(), limiter=_noop_limiter
            )
