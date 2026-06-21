"""Delta Chat client tests."""

# mypy: disable-error-code=no-untyped-def

from __future__ import annotations

import json
import sys
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

    def wait_for_event(self) -> SimpleNamespace:
        if self._event_sent:
            self._stop_event.wait(timeout=2.0)
            raise RuntimeError("stop")
        self._event_sent = True
        return SimpleNamespace(kind="IncomingMsg", msg_id=1)

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


def test_attachment_message_is_downloaded_before_processing() -> None:
    client, _ = _build_client()
    rpc = MagicMock()
    client._rpc = rpc
    account = SimpleNamespace(id=7)
    message = MagicMock()
    downloaded_snapshot = {
        "id": 46,
        "view_type": "Image",
        "download_state": "Done",
        "file": "/data/deltachat/blob/photo.png",
    }
    message.get_snapshot.return_value = downloaded_snapshot
    initial_snapshot = {
        "id": 46,
        "view_type": "Image",
        "download_state": "Available",
        "file": None,
    }

    result = client._wait_for_full_message(account, 46, message, initial_snapshot)

    rpc.download_full_message.assert_called_once_with(7, 46)
    assert result == downloaded_snapshot


def test_full_message_wait_returns_as_soon_as_file_is_available() -> None:
    client, _ = _build_client()
    rpc = MagicMock()
    client._rpc = rpc
    account = SimpleNamespace(id=7)
    message = MagicMock()
    snapshots = [
        {
            "id": 46,
            "view_type": "Audio",
            "download_state": "available",
            "file": None,
        },
        {
            "id": 46,
            "view_type": "Audio",
            "download_state": "available",
            "file": "/data/deltachat/blob/audio.ogg",
        },
        {
            "id": 46,
            "view_type": "Audio",
            "download_state": "done",
            "file": "/data/deltachat/blob/audio.ogg",
        },
    ]
    message.get_snapshot.side_effect = snapshots

    result = client._wait_for_full_message(account, 46, message, snapshots[0])

    rpc.download_full_message.assert_called_once_with(7, 46)
    assert result["file"] == "/data/deltachat/blob/audio.ogg"


def test_dcaccount_url_bootstrap_resolves_credentials(monkeypatch) -> None:
    client, _ = _build_client()

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {
                "address": "bootstrap@example.org",
                "password": "bootstrap-secret",
                "display_name": "Bootstrap Bot",
            }

    monkeypatch.setattr(
        "channels.delta_chat_channel.dc_client.httpx.post",
        lambda *_args, **_kwargs: _Response(),
    )
    config = DeltaChatAccountConfig(
        connector_id="delta-bootstrap",
        address="",
        password="",
        dcaccount_url="dcaccount:https://example.org/new",
        cw_account_id="1",
        cw_inbox_id="5",
    )

    resolved = client._resolve_bootstrap_config(config)

    assert resolved.address == "bootstrap@example.org"
    assert resolved.password == "bootstrap-secret"
    assert resolved.display_name == "Bootstrap Bot"


def test_dcaccount_url_is_not_reprovisioned_when_account_exists(monkeypatch) -> None:
    """A dcaccount_url mints a fresh address per call, so on a restart with an
    already-configured account we must reuse it, not POST /new again."""
    config = DeltaChatAccountConfig(
        connector_id="delta-bootstrap",
        dcaccount_url="dcaccount:https://example.org/new",
        cw_account_id="1",
        cw_inbox_id="5",
    )
    settings = DeltaChatSettings(
        delta_chat_accounts=[config],
        deltachat_accounts_dir="/tmp/deltachat",
        enable_native_deltachat_channel=True,
    )
    routing = DeltaChatRouting(settings.delta_chat_accounts)
    client = DeltaChatClient(settings, routing)

    stored = {
        "addr": "already@example.org",
        "ui.connector_id": "delta-bootstrap",
    }
    existing = MagicMock()
    existing.id = 11
    existing.get_config.side_effect = lambda key: stored.get(key)
    existing.is_configured.return_value = True

    client._deltachat = MagicMock()
    client._deltachat.get_all_accounts.return_value = [existing]

    def _fail_post(*_args, **_kwargs):
        raise AssertionError("dcaccount_url must not be fetched when account exists")

    monkeypatch.setattr(
        "channels.delta_chat_channel.dc_client.httpx.post", _fail_post
    )

    client._sync_accounts()

    # Reused the existing account, refreshed ui.* metadata, never re-added transport.
    existing.add_or_update_transport.assert_not_called()
    client._deltachat.add_account.assert_not_called()
    existing.set_config.assert_any_call("ui.cw_inbox_id", "5")
    runtime = client.get_runtime_account_by_connector_id("delta-bootstrap")
    assert runtime.account_id == 11
    assert runtime.address == "already@example.org"


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


class _PersistentAccount:
    def __init__(self, storage_dir: str, account_id: int, address: str | None) -> None:
        self.storage_dir = storage_dir
        self.id = account_id
        self._configured = address is not None
        self._config: dict[str, str | None] = {"addr": address}

    def get_config(self, key: str) -> str | None:
        return self._config.get(key)

    def is_configured(self) -> bool:
        return self._configured

    def add_or_update_transport(self, config: dict[str, str]) -> None:
        self._config["addr"] = config["addr"]
        self._config["password"] = config["password"]
        self._configured = True
        self._persist()

    def set_config(self, key: str, value: str) -> None:
        self._config[key] = value
        self._persist()

    def set_avatar(self, avatar_path: str) -> None:
        self._config["avatar_path"] = avatar_path
        self._persist()

    def _persist(self) -> None:
        return None


class _PersistentDeltaChat:
    def __init__(self, rpc: object) -> None:
        self._storage_dir = getattr(rpc, "accounts_dir")
        self._accounts_file = f"{self._storage_dir}/accounts.json"
        self._accounts: list[_PersistentAccount] = []
        try:
            with open(self._accounts_file, "r", encoding="utf-8") as file_handle:
                data = json.load(file_handle)
        except FileNotFoundError:
            data = []
        for item in data:
            self._accounts.append(
                _PersistentAccount(self._storage_dir, int(item["id"]), item["addr"])
            )

    def _save(self) -> None:
        payload = [
            {"id": account.id, "addr": account.get_config("addr")}
            for account in self._accounts
        ]
        with open(self._accounts_file, "w", encoding="utf-8") as file_handle:
            json.dump(payload, file_handle)

    def get_all_accounts(self) -> list[_PersistentAccount]:
        return self._accounts

    def add_account(self) -> _PersistentAccount:
        account = _PersistentAccount(
            self._storage_dir, len(self._accounts) + 1, None
        )
        account._persist = self._save  # type: ignore[method-assign]
        self._accounts.append(account)
        self._save()
        return account

    def start_io(self) -> None:
        return None

    def stop_io(self) -> None:
        return None


class _PersistentRpc:
    def __init__(self, *, accounts_dir: str, rpc_server_path: str) -> None:
        self.accounts_dir = accounts_dir
        self.rpc_server_path = rpc_server_path

    def start(self) -> None:
        return None

    def close(self) -> None:
        return None


def test_connector_mapping_survives_restart(monkeypatch, tmp_path) -> None:
    fake_module = SimpleNamespace(Rpc=_PersistentRpc, DeltaChat=_PersistentDeltaChat)
    monkeypatch.setitem(sys.modules, "deltachat_rpc_client", fake_module)

    account_config_1 = DeltaChatAccountConfig(
        connector_id="delta-client-1",
        address="bot1@example.org",
        password="secret",
        cw_account_id="1",
        cw_inbox_id="5",
    )
    account_config_2 = DeltaChatAccountConfig(
        connector_id="delta-client-2",
        address="bot2@example.org",
        password="secret",
        cw_account_id="1",
        cw_inbox_id="6",
    )
    settings = DeltaChatSettings(
        delta_chat_accounts=[account_config_1, account_config_2],
        deltachat_accounts_dir=str(tmp_path / "deltachat"),
        enable_native_deltachat_channel=True,
    )
    routing = DeltaChatRouting(settings.delta_chat_accounts)

    first_client = DeltaChatClient(settings, routing)
    first_client.start()
    first_account_id = first_client.get_runtime_account_by_connector_id(
        "delta-client-1"
    ).account_id
    second_account_id = first_client.get_runtime_account_by_connector_id(
        "delta-client-2"
    ).account_id
    first_client.stop()

    second_client = DeltaChatClient(settings, routing)
    second_client.start()

    assert second_client.get_runtime_account_by_connector_id("delta-client-1").account_id == first_account_id
    assert second_client.get_runtime_account_by_connector_id("delta-client-2").account_id == second_account_id
    assert second_client.get_runtime_account_by_account_id(first_account_id).connector_id == "delta-client-1"
    assert second_client.get_runtime_account_by_account_id(second_account_id).connector_id == "delta-client-2"
    second_client.stop()
