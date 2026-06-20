from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from channels.delta_chat_channel.dc_attachments import extract_delta_chat_attachments
from channels.delta_chat_channel.dc_models import (
    DeltaChatAccountConfig,
    DeltaChatRuntimeAccount,
)
from channels.delta_chat_channel.dc_routing import DeltaChatRouting
from channels.delta_chat_channel.dc_settings import DeltaChatSettings


class DeltaChatClient:
    def __init__(
        self,
        settings: DeltaChatSettings,
        routing: DeltaChatRouting,
    ) -> None:
        self._settings = settings
        self._routing = routing
        self._rpc: Any | None = None
        self._deltachat: Any | None = None
        self._accounts_by_connector_id: dict[str, DeltaChatRuntimeAccount] = {}
        self._accounts_by_account_id: dict[int, DeltaChatRuntimeAccount] = {}
        self._account_objects_by_connector_id: dict[str, Any] = {}
        self._account_objects_by_account_id: dict[int, Any] = {}
        self._new_message_handler: Callable[
            [DeltaChatRuntimeAccount, dict[str, Any]], None
        ] | None = None
        self._stop_event = threading.Event()
        self._event_threads: list[threading.Thread] = []

    def set_new_message_handler(
        self, handler: Callable[[DeltaChatRuntimeAccount, dict[str, Any]], None]
    ) -> None:
        self._new_message_handler = handler

    @property
    def is_native_enabled(self) -> bool:
        return self._settings.enable_native_deltachat_channel

    def start(self) -> None:
        if not self._settings.enable_native_deltachat_channel:
            return
        if self._rpc is not None:
            return

        from deltachat_rpc_client import DeltaChat, Rpc

        accounts_dir = Path(self._settings.deltachat_accounts_dir)
        accounts_dir.mkdir(parents=True, exist_ok=True)

        self._rpc = Rpc(
            accounts_dir=str(accounts_dir),
            rpc_server_path=self._settings.deltachat_rpc_server_path,
        )
        self._rpc.start()
        self._deltachat = DeltaChat(self._rpc)
        self._sync_accounts()
        self._deltachat.start_io()
        self._start_event_threads()

    def stop(self) -> None:
        if not self._settings.enable_native_deltachat_channel:
            return
        self._stop_event.set()
        if self._deltachat is not None:
            self._deltachat.stop_io()
        for thread in self._event_threads:
            thread.join(timeout=1.0)
        if self._rpc is not None:
            self._rpc.close()
        self._rpc = None
        self._deltachat = None
        self._accounts_by_connector_id.clear()
        self._accounts_by_account_id.clear()
        self._account_objects_by_connector_id.clear()
        self._account_objects_by_account_id.clear()
        self._event_threads.clear()
        self._stop_event.clear()

    def _sync_accounts(self) -> None:
        if self._deltachat is None:
            raise RuntimeError("Delta Chat client not started")

        existing_accounts = self._deltachat.get_all_accounts()
        accounts_by_address = {
            str(account.get_config("addr") or "").strip().lower(): account
            for account in existing_accounts
            if account.get_config("addr")
        }

        for config in self._settings.delta_chat_accounts:
            account = self._ensure_account(config, accounts_by_address)
            runtime_account = DeltaChatRuntimeAccount(
                connector_id=config.connector_id,
                account_id=account.id,
                address=config.address,
                storage_dir=self._resolved_storage_dir(config),
            )
            self._accounts_by_connector_id[config.connector_id] = runtime_account
            self._accounts_by_account_id[account.id] = runtime_account
            self._account_objects_by_connector_id[config.connector_id] = account
            self._account_objects_by_account_id[account.id] = account
            self._routing.register_account_id(config.connector_id, account.id)

    def _ensure_account(
        self,
        config: DeltaChatAccountConfig,
        accounts_by_address: dict[str, Any],
    ) -> Any:
        if self._deltachat is None:
            raise RuntimeError("Delta Chat client not started")

        address = config.address.strip().lower()
        account = accounts_by_address.get(address)
        if account is None:
            account = self._deltachat.add_account()

        if not account.is_configured():
            account.configure(config.address, config.password)

        account.set_config("displayname", config.display_name or config.address)
        if config.avatar_path:
            account.set_avatar(config.avatar_path)
        account.set_config("ui.connector_id", config.connector_id)
        account.set_config("ui.cw_account_id", config.cw_account_id)
        account.set_config("ui.cw_inbox_id", config.cw_inbox_id)
        account.set_config("ui.storage_dir", self._resolved_storage_dir(config))
        return account

    def _resolved_storage_dir(self, config: DeltaChatAccountConfig) -> str:
        if config.storage_dir:
            return config.storage_dir
        return str(Path(self._settings.deltachat_accounts_dir) / config.connector_id)

    def get_account(self, connector_id: str) -> Any:
        account = self._account_objects_by_connector_id.get(connector_id)
        if account is None:
            raise KeyError(f"Unknown connector_id={connector_id}")
        return account

    def get_runtime_account_by_connector_id(
        self, connector_id: str
    ) -> DeltaChatRuntimeAccount:
        runtime_account = self._accounts_by_connector_id.get(connector_id)
        if runtime_account is None:
            raise KeyError(f"Unknown connector_id={connector_id}")
        return runtime_account

    def get_runtime_account_by_account_id(
        self, account_id: int
    ) -> DeltaChatRuntimeAccount:
        runtime_account = self._accounts_by_account_id.get(account_id)
        if runtime_account is None:
            raise KeyError(f"Unknown account_id={account_id}")
        return runtime_account

    def register_message_handler(
        self, handler: Callable[[DeltaChatRuntimeAccount, dict[str, Any]], None]
    ) -> None:
        self._new_message_handler = handler
        if self._deltachat is not None and not self._event_threads:
            self._start_event_threads()

    @property
    def new_message_handler(
        self,
    ) -> Callable[[DeltaChatRuntimeAccount, dict[str, Any]], None] | None:
        return self._new_message_handler

    def _start_event_threads(self) -> None:
        if self._new_message_handler is None:
            return

        for runtime_account in self._accounts_by_connector_id.values():
            thread = threading.Thread(
                target=self._event_loop,
                args=(runtime_account,),
                daemon=True,
                name=f"deltachat-events-{runtime_account.connector_id}",
            )
            thread.start()
            self._event_threads.append(thread)

    def _event_loop(self, runtime_account: DeltaChatRuntimeAccount) -> None:
        while not self._stop_event.is_set():
            try:
                account = self.get_account(runtime_account.connector_id)
                event = account.wait_for_incoming_msg_event()
            except Exception:
                if self._stop_event.is_set():
                    return
                continue

            if self._stop_event.is_set() or self._new_message_handler is None:
                continue

            try:
                message = account.get_message_by_id(int(event.msg_id))
                snapshot = message.get_snapshot()
                sender_contact = message.get_sender_contact()
                sender_snapshot = sender_contact.get_snapshot()
                chat_snapshot: dict[str, Any] = {}
                chat_id = snapshot.get("chat_id")
                if chat_id is not None:
                    chat_snapshot = account.get_chat_by_id(int(chat_id)).get_basic_snapshot()

                attachments = extract_delta_chat_attachments(snapshot)

                payload = {
                    "account_id": runtime_account.account_id,
                    "connector_id": runtime_account.connector_id,
                    "message_id": str(snapshot.get("id") or event.msg_id),
                    "chat_id": str(chat_id or ""),
                    "sender_id": str(sender_snapshot.get("id") or ""),
                    "sender_address": str(
                        sender_snapshot.get("address")
                        or sender_snapshot.get("email")
                        or ""
                    ),
                    "sender_name": sender_snapshot.get("display_name")
                    or sender_snapshot.get("name"),
                    "text": str(snapshot.get("text") or ""),
                    "attachments": attachments,
                    "is_group": str(chat_snapshot.get("chat_type") or "").upper()
                    == "GROUP",
                    "is_info": bool(snapshot.get("is_info")),
                }
                if payload["sender_address"].strip().lower() == runtime_account.address.strip().lower():
                    continue
                self._new_message_handler(runtime_account, payload)
            except Exception:
                continue
