"""Delta Chat client tests."""

# mypy: disable-error-code=no-untyped-def

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

from channels.delta_chat_channel.dc_client import DeltaChatClient
from channels.delta_chat_channel.dc_models import DeltaChatAccountConfig, DeltaChatRuntimeAccount
from channels.delta_chat_channel.dc_routing import DeltaChatRouting
from channels.delta_chat_channel.dc_settings import DeltaChatSettings


class _LoopAccount:
    def __init__(self, *, sender_address: str, stop_event: threading.Event) -> None:
        self.sender_address = sender_address
        self._stop_event = stop_event
        self._event_sent = False

    def wait_for_incoming_msg_event(self) -> SimpleNamespace:
        if self._event_sent:
            self._stop_event.wait(timeout=2.0)
            raise RuntimeError("stop")
        self._event_sent = True
        return SimpleNamespace(msg_id=1)

    def get_message_by_id(self, _msg_id: int) -> MagicMock:
        message = MagicMock()
        message.get_snapshot.return_value = {
            "id": "msg-1",
            "chat_id": 1,
            "text": "Hello",
            "file": None,
            "is_info": False,
        }
        message.get_sender_contact.return_value.get_snapshot.return_value = {
            "id": "sender-1",
            "address": self.sender_address,
            "display_name": "Delta User",
        }
        return message

    def get_chat_by_id(self, _chat_id: int) -> MagicMock:
        chat = MagicMock()
        chat.get_basic_snapshot.return_value = {"chat_type": "single"}
        return chat


def _build_client() -> tuple[DeltaChatClient, DeltaChatRuntimeAccount]:
    account_config = DeltaChatAccountConfig(
        connector_id="delta-client-1",
        address="bot1@example.org",
        password="secret",
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
    runtime_account = DeltaChatRuntimeAccount(
        connector_id="delta-client-1",
        account_id=7,
        address="bot1@example.org",
        storage_dir="/tmp/deltachat/delta-client-1",
    )
    client._accounts_by_connector_id[runtime_account.connector_id] = runtime_account
    client._accounts_by_account_id[runtime_account.account_id] = runtime_account
    return client, runtime_account


def test_rpc_listener_shutdown_clears_state() -> None:
    client, _ = _build_client()
    rpc = MagicMock()
    deltachat = MagicMock()
    client._rpc = rpc
    client._deltachat = deltachat
    client._event_threads = []

    client.stop()

    deltachat.stop_io.assert_called_once()
    rpc.close.assert_called_once()
    assert client._rpc is None
    assert client._deltachat is None


def test_own_messages_are_ignored() -> None:
    client, runtime_account = _build_client()
    stop_event = client._stop_event
    account = _LoopAccount(sender_address=runtime_account.address, stop_event=stop_event)
    client.get_account = MagicMock(return_value=account)  # type: ignore[method-assign]
    handler = MagicMock()
    client._new_message_handler = handler

    thread = threading.Thread(target=client._event_loop, args=(runtime_account,))
    thread.start()
    stop_event.set()
    thread.join(timeout=2.0)

    handler.assert_not_called()


def test_failure_of_one_account_does_not_stop_another() -> None:
    client, runtime_account = _build_client()
    stop_event = client._stop_event
    bad_runtime = DeltaChatRuntimeAccount(
        connector_id="delta-client-2",
        account_id=8,
        address="bot2@example.org",
        storage_dir="/tmp/deltachat/delta-client-2",
    )
    good_account = _LoopAccount(sender_address="user@example.org", stop_event=stop_event)

    def _get_account(connector_id: str) -> object:
        if connector_id == runtime_account.connector_id:
            return good_account
        raise RuntimeError("broken account")

    client.get_account = MagicMock(side_effect=_get_account)  # type: ignore[method-assign]
    received: list[dict[str, object]] = []

    def _handler(_runtime_account: DeltaChatRuntimeAccount, payload: dict[str, object]) -> None:
        received.append(payload)
        stop_event.set()

    client._new_message_handler = _handler
    client._accounts_by_connector_id[bad_runtime.connector_id] = bad_runtime

    good_thread = threading.Thread(target=client._event_loop, args=(runtime_account,))
    bad_thread = threading.Thread(target=client._event_loop, args=(bad_runtime,))
    good_thread.start()
    bad_thread.start()
    good_thread.join(timeout=2.0)
    bad_thread.join(timeout=2.0)

    assert received
    assert received[0]["sender_address"] == "user@example.org"
