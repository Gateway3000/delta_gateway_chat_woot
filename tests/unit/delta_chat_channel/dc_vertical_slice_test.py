from __future__ import annotations

import asyncio
import sys
import threading
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from channels.delta_chat_channel.dc_channel import DeltaChatChannel
from channels.delta_chat_channel.dc_client import DeltaChatClient
from channels.delta_chat_channel.dc_message_processor import DeltaChatMessageProcessor
from channels.delta_chat_channel.dc_models import DeltaChatAccountConfig
from channels.delta_chat_channel.dc_routing import DeltaChatRouting
from channels.delta_chat_channel.dc_settings import DeltaChatSettings
from channels.delta_chat_channel.dc_transport import DeltaChatTransport


class _FakeSenderContact:
    def get_snapshot(self) -> dict[str, object]:
        return {
            "id": "sender-1",
            "address": "user@example.org",
            "display_name": "Delta User",
        }


class _FakeChat:
    def get_basic_snapshot(self) -> dict[str, object]:
        return {"chat_type": "single"}


class _FakeMessage:
    def get_snapshot(self) -> dict[str, object]:
        return {
            "id": "msg-1",
            "chat_id": 1,
            "text": "Hello from Delta Chat",
            "file": None,
            "is_info": False,
        }

    def get_sender_contact(self) -> _FakeSenderContact:
        return _FakeSenderContact()


class _FakeAccount:
    def __init__(self, stop_release: threading.Event) -> None:
        self.id = 7
        self._event_sent = False
        self._stop_release = stop_release

    def get_config(self, key: str) -> str | None:
        return {"addr": "bot1@example.org"}.get(key)

    def is_configured(self) -> bool:
        return True

    def configure(self, *_args: object, **_kwargs: object) -> None:
        return None

    def set_config(self, *_args: object, **_kwargs: object) -> None:
        return None

    def set_avatar(self, *_args: object, **_kwargs: object) -> None:
        return None

    def wait_for_incoming_msg_event(self) -> SimpleNamespace:
        if not self._event_sent:
            self._event_sent = True
            return SimpleNamespace(msg_id=99)
        self._stop_release.wait(timeout=5.0)
        raise RuntimeError("listener stopped")

    def get_message_by_id(self, _msg_id: int) -> _FakeMessage:
        return _FakeMessage()

    def get_chat_by_id(self, _chat_id: int) -> _FakeChat:
        return _FakeChat()


class _FakeDeltaChat:
    def __init__(self, rpc: object, account: _FakeAccount) -> None:
        self._rpc = rpc
        self._account = account

    def get_all_accounts(self) -> list[_FakeAccount]:
        return [self._account]

    def add_account(self) -> _FakeAccount:
        return self._account

    def start_io(self) -> None:
        return None

    def stop_io(self) -> None:
        return None


class _FakeRpc:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        return None

    def start(self) -> None:
        return None

    def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_text_only_round_trip_with_mocked_rpc_boundary(monkeypatch) -> None:
    stop_release = threading.Event()
    fake_account = _FakeAccount(stop_release)

    fake_module = types.SimpleNamespace(
        Rpc=_FakeRpc,
        DeltaChat=lambda rpc: _FakeDeltaChat(rpc, fake_account),
    )
    monkeypatch.setitem(sys.modules, "deltachat_rpc_client", fake_module)

    account_config = DeltaChatAccountConfig(
        connector_id="delta-client-1",
        address="bot1@example.org",
        password="secret",
        display_name="Support Bot 1",
        cw_account_id="1",
        cw_inbox_id="5",
    )
    settings = DeltaChatSettings(
        delta_chat_accounts=[account_config],
        deltachat_accounts_dir="/tmp/deltachat",
        enable_native_deltachat_channel=True,
    )
    routing = DeltaChatRouting(settings.delta_chat_accounts)
    client = DeltaChatClient(settings, routing)

    identity_store = MagicMock()
    identity_store.get_or_create_actor_id = AsyncMock(return_value="delta_chat_actor_1")
    identity_store.resolve_external_id = AsyncMock(return_value="user@example.org")

    mq = AsyncMock()
    mq.is_already_processed = AsyncMock(return_value=False)
    mq.mark_as_processed = AsyncMock()
    queue_event = asyncio.Event()

    async def _send_side_effect(queue_name: str, payload: dict[str, object]) -> None:
        assert queue_name == "to_cw"
        queue_event.set()

    mq.send = AsyncMock(side_effect=_send_side_effect)

    transport = DeltaChatTransport(settings, routing, client, identity_store)
    processor = DeltaChatMessageProcessor(
        routing,
        transport,
        identity_store,
        mq,
        "to_cw",
        "from_cw",
    )
    channel = DeltaChatChannel(routing, client, transport, processor)

    await channel.on_startup()
    await asyncio.wait_for(queue_event.wait(), timeout=5.0)

    mq.send.assert_awaited_once()
    queue_name, payload = mq.send.await_args.args
    assert queue_name == "to_cw"
    assert payload["channel"] == "delta_chat"
    assert payload["from_"] == "delta_chat"
    assert payload["to"] == "chatwoot"
    assert payload["connector_id"] == "delta-client-1"
    assert payload["cw_account_id"] == "1"
    assert payload["cw_inbox_id"] == "5"
    assert payload["message_id"] == "msg-1"
    assert payload["sender"]["external_id"] == "delta_chat_actor_1"
    assert payload["sender"]["raw_external_id"] == "user@example.org"
    assert payload["payload"]["text"] == "Hello from Delta Chat"
    assert payload["payload"]["chat_id"] == "1"

    stop_release.set()
    await channel.on_shutdown()

    identity_store.get_or_create_actor_id.assert_awaited_once_with(
        "delta_chat", "user@example.org"
    )
    mq.mark_as_processed.assert_awaited_once()
