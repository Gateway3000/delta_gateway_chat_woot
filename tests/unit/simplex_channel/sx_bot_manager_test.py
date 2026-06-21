import pytest

from channels.simplex_channel.sx_bot_manager import SimplexConnection, _unwrap, SimplexError
from tests.unit.simplex_channel.conftest import make_new_chat_items_event


def _conn() -> SimplexConnection:
    return SimplexConnection(
        connector_id="sx1",
        ws_url="ws://simplex-chat:5225",
        user_id=1,
        send_timeout=5.0,
        reconnect_delay=1.0,
    )


class TestEventFiltering:
    def test_one_to_one_received_text_is_emitted(self) -> None:
        conn = _conn()
        conn._handle_event(make_new_chat_items_event())

        assert conn.inbound.qsize() == 1
        item = conn.inbound.get_nowait()
        assert item["type"] == "message"
        assert item["source_id"] == 42
        assert item["item_id"] == 1001
        assert item["text"] == "Hi"

    @pytest.mark.parametrize(
        "mutation",
        [
            {"chat_type": "group"},  # group, not 1:1
            {"dir_type": "directSnd"},  # our own outgoing echoed back
            {"content_type": "image"},  # non-text content
            {"text": "   "},  # empty after strip
        ],
    )
    def test_non_one_to_one_text_is_dropped(self, mutation: dict) -> None:
        conn = _conn()
        conn._handle_event(make_new_chat_items_event(**mutation))
        assert conn.inbound.qsize() == 0


class TestUnwrap:
    def test_unwraps_either_right(self) -> None:
        assert _unwrap({"Right": {"type": "ok"}}) == {"type": "ok"}

    def test_flat_payload_passthrough(self) -> None:
        assert _unwrap({"type": "userContactLink"}) == {"type": "userContactLink"}

    def test_either_left_raises(self) -> None:
        with pytest.raises(SimplexError):
            _unwrap({"Left": {"type": "error"}})

    def test_flat_error_raises(self) -> None:
        with pytest.raises(SimplexError):
            _unwrap({"type": "chatCmdError"})
