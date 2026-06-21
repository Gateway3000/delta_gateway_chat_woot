from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

import httpx
import structlog
from channels.delta_chat_channel.dc_attachments import extract_delta_chat_attachments
from channels.delta_chat_channel.dc_models import (
    DeltaChatAccountConfig,
    DeltaChatRuntimeAccount,
)
from channels.delta_chat_channel.dc_routing import DeltaChatRouting
from channels.delta_chat_channel.dc_settings import DeltaChatSettings

logger = structlog.get_logger(__name__)


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
        self._lifecycle_lock = threading.Lock()
        self._event_threads: list[threading.Thread] = []
        self._event_thread_connectors: set[str] = set()

    def set_new_message_handler(
        self, handler: Callable[[DeltaChatRuntimeAccount, dict[str, Any]], None]
    ) -> None:
        self._new_message_handler = handler

    @property
    def is_native_enabled(self) -> bool:
        return self._settings.enable_native_deltachat_channel

    def start(self) -> None:
        with self._lifecycle_lock:
            self._start_locked()

    def _start_locked(self) -> None:
        if not self._settings.enable_native_deltachat_channel or self._rpc is not None:
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

    def get_secure_join_qr_svg(self, connector_id: str) -> str:
        account = self.get_account(connector_id)
        _qr_data, svg = account.get_qr_code_svg()
        return svg

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
        accounts_by_connector_id = {
            str(account.get_config("ui.connector_id") or ""): account
            for account in existing_accounts
            if account.get_config("ui.connector_id")
        }

        for config in self._settings.delta_chat_accounts:
            existing = accounts_by_connector_id.get(config.connector_id)
            reuse = bool(
                config.dcaccount_url
                and existing is not None
                and existing.is_configured()
            )
            if reuse:
                # A dcaccount_url mints a brand-new random address on every call,
                # so provisioning must happen only once. On later boots reuse the
                # already-configured account for this connector instead of minting
                # (and re-configuring) a fresh one — which both loses the bot's
                # identity and re-runs the slow mail-server login each start.
                effective_config = config.model_copy(
                    update={"address": str(existing.get_config("addr") or "")}
                )
                account = existing
            else:
                effective_config = self._resolve_bootstrap_config(config)
                address = effective_config.address.strip().lower()
                account = accounts_by_address.get(address)
                if account is None:
                    account = self._deltachat.add_account()

            runtime_account = DeltaChatRuntimeAccount(
                connector_id=effective_config.connector_id,
                account_id=account.id,
                address=effective_config.address,
                storage_dir=self._resolved_storage_dir(effective_config),
            )
            self._accounts_by_connector_id[effective_config.connector_id] = runtime_account
            self._accounts_by_account_id[account.id] = runtime_account
            self._account_objects_by_connector_id[effective_config.connector_id] = account
            self._account_objects_by_account_id[account.id] = account
            self._routing.register_account_id(effective_config.connector_id, account.id)

            # Start the event pump *before* configuring the transport so the
            # core's ConfigureProgress / Warning / Error events are logged live.
            # Otherwise a failing IMAP/SMTP login just blocks startup silently.
            self._start_event_thread(runtime_account)

            if reuse:
                self._refresh_account_metadata(account, effective_config)
                logger.info(
                    "Delta Chat account reused",
                    connector_id=effective_config.connector_id,
                    address=effective_config.address,
                )
                continue

            logger.info(
                "Delta Chat configuring account transport",
                connector_id=effective_config.connector_id,
                address=effective_config.address,
            )
            account.add_or_update_transport(
                {"addr": effective_config.address, "password": effective_config.password}
            )
            self._refresh_account_metadata(account, effective_config)
            logger.info(
                "Delta Chat account configured",
                connector_id=effective_config.connector_id,
                address=effective_config.address,
                is_configured=account.is_configured(),
            )

    def _resolve_bootstrap_config(self, config: DeltaChatAccountConfig) -> DeltaChatAccountConfig:
        if not config.dcaccount_url:
            return config

        credentials = self._load_dcaccount_credentials(config.dcaccount_url)
        address = str(
            credentials.get("address")
            or credentials.get("addr")
            or credentials.get("username")
            or credentials.get("email")
            or config.address
            or ""
        ).strip()
        password = str(
            credentials.get("password")
            or credentials.get("pass")
            or credentials.get("mail_pw")
            or config.password
            or ""
        )
        if not address or not password:
            raise ValueError(
                f"dcaccount_url for connector_id={config.connector_id} did not return address/password"
            )

        display_name = str(
            credentials.get("display_name")
            or credentials.get("displayname")
            or credentials.get("name")
            or config.display_name
            or ""
        ).strip() or None

        avatar_path = config.avatar_path
        if isinstance(credentials.get("avatar_path"), str) and credentials["avatar_path"].strip():
            avatar_path = str(credentials["avatar_path"]).strip()

        return config.model_copy(
            update={
                "address": address,
                "password": password,
                "display_name": display_name,
                "avatar_path": avatar_path,
            }
        )

    def _load_dcaccount_credentials(self, dcaccount_url: str) -> dict[str, Any]:
        url = dcaccount_url.strip()
        # The DCACCOUNT QR/URL is "DCACCOUNT:<https url>" (case-insensitive);
        # the real chatmail endpoint is the inner https URL.
        if url.lower().startswith("dcaccount:"):
            url = url[len("dcaccount:") :]
        if not url:
            raise ValueError("dcaccount_url is empty")

        # chatmail account creation is a POST to /new that returns
        # {"email", "password"} as JSON. A GET instead returns a 301 whose
        # Location is the "dcaccount:" QR string (meant for a Delta Chat app),
        # which is not a followable HTTP URL — so POST and don't chase redirects.
        response = httpx.post(url, timeout=15.0, follow_redirects=False)
        response.raise_for_status()
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ValueError(f"dcaccount_url did not return valid JSON: {url}") from exc
        if isinstance(payload, dict) and isinstance(payload.get("payload"), dict):
            payload = payload["payload"]
        if not isinstance(payload, dict):
            raise ValueError(f"dcaccount_url must return a JSON object: {url}")
        return payload

    def _refresh_account_metadata(
        self, account: Any, config: DeltaChatAccountConfig
    ) -> Any:
        """Apply display/ui config to an account without (re)configuring its
        transport — safe to call for an already-configured account."""
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
        if self._deltachat is not None:
            self._start_event_threads()

    @property
    def new_message_handler(
        self,
    ) -> Callable[[DeltaChatRuntimeAccount, dict[str, Any]], None] | None:
        return self._new_message_handler

    def _start_event_threads(self) -> None:
        for runtime_account in self._accounts_by_connector_id.values():
            self._start_event_thread(runtime_account)

    def _start_event_thread(self, runtime_account: DeltaChatRuntimeAccount) -> None:
        if runtime_account.connector_id in self._event_thread_connectors:
            return
        self._event_thread_connectors.add(runtime_account.connector_id)
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
                event = account.wait_for_event()
            except Exception:
                if self._stop_event.is_set():
                    return
                continue

            if self._stop_event.is_set():
                continue

            kind = str(getattr(event, "kind", "") or "")
            if kind != "IncomingMsg":
                self._log_core_event(runtime_account.connector_id, kind, event)
                continue

            if self._new_message_handler is None:
                continue

            try:
                message = account.get_message_by_id(int(event.msg_id))
                snapshot = message.get_snapshot()
                snapshot = self._wait_for_full_message(
                    account, int(event.msg_id), message, snapshot
                )
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

    def _log_core_event(self, connector_id: str, kind: str, event: Any) -> None:
        """Surface Delta Chat core lifecycle events so configuration/connection
        problems are visible instead of silently blocking startup."""
        if kind == "Error":
            logger.error(
                "Delta Chat core error",
                connector_id=connector_id,
                msg=getattr(event, "msg", None),
            )
        elif kind == "Warning":
            logger.warning(
                "Delta Chat core warning",
                connector_id=connector_id,
                msg=getattr(event, "msg", None),
            )
        elif kind == "ConfigureProgress":
            logger.info(
                "Delta Chat configure progress",
                connector_id=connector_id,
                progress=getattr(event, "progress", None),
                comment=getattr(event, "comment", None),
            )
        elif kind in ("ConnectivityChanged", "ImapConnected", "ImapInboxIdle"):
            logger.info(
                "Delta Chat connectivity event",
                connector_id=connector_id,
                kind=kind,
            )
        elif kind == "Info":
            logger.debug(
                "Delta Chat core info",
                connector_id=connector_id,
                msg=getattr(event, "msg", None),
            )

    def _wait_for_full_message(
        self,
        account: Any,
        message_id: int,
        message: Any,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        view_type = str(snapshot.get("view_type") or "").strip().lower()
        download_state = str(snapshot.get("download_state") or "").strip().lower()
        needs_download = (
            view_type not in {"", "text"}
            and not snapshot.get("file")
            and download_state != "done"
        )
        if not needs_download or self._rpc is None:
            return snapshot

        self._rpc.download_full_message(account.id, message_id)
        deadline = (
            time.monotonic()
            + self._settings.deltachat_attachment_download_timeout_seconds
        )
        while time.monotonic() < deadline and not self._stop_event.is_set():
            snapshot = message.get_snapshot()
            if snapshot.get("file"):
                return snapshot
            if str(snapshot.get("download_state") or "").lower() == "done":
                return snapshot
            time.sleep(0.2)
        return snapshot
