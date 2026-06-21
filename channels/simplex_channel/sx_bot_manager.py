from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp
import structlog

from channels.simplex_channel.plugin_settings import BotConfig

logger = structlog.get_logger(__name__)


class SimplexError(Exception):
    """A failure talking to the simplex-chat CLI.

    `transient` distinguishes a recoverable problem (connection dropped,
    timeout) — mapped by the transport to a retryable TransientError — from a
    permanent one (the CLI rejected the command).
    """

    def __init__(self, message: str, *, transient: bool = False):
        self.transient = transient
        super().__init__(message)


def _unwrap(resp: dict[str, Any]) -> dict[str, Any]:
    """Normalize the response payload across CLI versions.

    Older CLIs wrap results in a Haskell `Either` (`{"Right": ...}` /
    `{"Left": ...}`); newer ones return the record flat. Raises SimplexError
    for `Left`/error payloads.
    """
    if "Left" in resp:
        raise SimplexError(f"simplex-chat error: {resp['Left']}")
    payload = resp.get("Right", resp)
    if isinstance(payload, dict) and payload.get("type") in {
        "chatCmdError",
        "chatError",
    }:
        raise SimplexError(f"simplex-chat command error: {payload}")
    return payload


def _unwrap_event(resp: dict[str, Any]) -> dict[str, Any]:
    """Like `_unwrap` but for async events — never raises on error payloads."""
    return resp.get("Right", resp) if isinstance(resp, dict) else {}


class SimplexConnection:
    """A persistent WebSocket client for one simplex-chat CLI instance.

    The CLI speaks JSON over WebSocket: requests are `{"corrId","cmd"}` and
    replies carry the matching `corrId`; asynchronous events (incoming
    messages, new contacts) arrive with a null/absent `corrId`. This class
    keeps a single connection alive (reconnecting on drop), correlates command
    replies to `send_command` callers by `corrId`, and normalizes incoming
    1:1 text `newChatItems` events onto `inbound` for the receiver.
    """

    def __init__(
        self,
        connector_id: str,
        ws_url: str,
        user_id: int,
        send_timeout: float,
        reconnect_delay: float,
    ):
        self.connector_id = connector_id
        self.ws_url = ws_url
        self.user_id = user_id
        self._send_timeout = send_timeout
        self._reconnect_delay = reconnect_delay

        self.inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._corr_id = 0
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._connected = asyncio.Event()
        self._stopping = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(
                self._run(), name=f"simplex_conn_{self.connector_id}"
            )

    async def close(self) -> None:
        self._stopping.set()
        if self._ws is not None:
            await self._ws.close()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def send_command(self, command: str) -> dict[str, Any]:
        """Send a CLI command and await its (normalized) response payload."""
        if self._ws is None or not self._connected.is_set():
            raise SimplexError("not connected to simplex-chat", transient=True)

        self._corr_id += 1
        corr_id = str(self._corr_id)
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[corr_id] = future
        try:
            await self._ws.send_json({"corrId": corr_id, "cmd": command})
        except (aiohttp.ClientError, ConnectionError) as exc:
            self._pending.pop(corr_id, None)
            raise SimplexError(f"failed to send command: {exc!r}", transient=True) from exc

        try:
            resp = await asyncio.wait_for(future, timeout=self._send_timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(corr_id, None)
            raise SimplexError("timed out waiting for simplex-chat reply", transient=True) from exc
        return _unwrap(resp)

    async def send_text(self, contact_id: str, text: str) -> dict[str, Any]:
        # ChatRef syntax is "<chatType><chatId>"; "@" is a direct contact.
        composed = [{"msgContent": {"type": "text", "text": text}}]
        command = f"/_send @{contact_id} json {json.dumps(composed)}"
        return await self.send_command(command)

    async def setup_address(self) -> None:
        """Ensure the bot has an address that auto-accepts contact requests."""
        try:
            await self.send_command(f"/_address {self.user_id}")
        except SimplexError as exc:
            # Address very likely already exists from a previous run — fine.
            logger.debug(
                "simplex address create skipped",
                connector_id=self.connector_id,
                detail=str(exc),
            )
        settings = {"businessAddress": False, "autoAccept": {"acceptIncognito": False}}
        try:
            await self.send_command(
                f"/_address_settings {self.user_id} {json.dumps(settings)}"
            )
            address = await self.send_command(f"/_show_address {self.user_id}")
            # Response shape: {..., "contactLink": {"connLinkContact":
            #   {"connFullLink": ..., "connShortLink": ...}}}
            link = (address.get("contactLink") or {}).get("connLinkContact") or {}
            logger.info(
                "SimpleX bot address ready (share it so users can connect)",
                connector_id=self.connector_id,
                address=link.get("connShortLink") or link.get("connFullLink"),
                full_link=link.get("connFullLink"),
            )
        except SimplexError as exc:
            logger.warning(
                "could not configure simplex auto-accept",
                connector_id=self.connector_id,
                error=str(exc),
            )

    async def _run(self) -> None:
        while not self._stopping.is_set():
            reader_task: asyncio.Task[None] | None = None
            try:
                self._session = aiohttp.ClientSession()
                self._ws = await self._session.ws_connect(self.ws_url, heartbeat=30)
                self._connected.set()
                logger.info(
                    "Connected to simplex-chat",
                    connector_id=self.connector_id,
                    ws_url=self.ws_url,
                )
                # The read loop must run concurrently with setup: send_command
                # awaits a reply that only the read loop can deliver, so start
                # reading first, then configure the address.
                reader_task = asyncio.create_task(self._read_loop(self._ws))
                await self.setup_address()
                await reader_task
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "simplex-chat connection error",
                    connector_id=self.connector_id,
                    error=repr(exc),
                )
            finally:
                self._connected.clear()
                self._ws = None
                if reader_task is not None and not reader_task.done():
                    reader_task.cancel()
                if self._session is not None:
                    await self._session.close()
                    self._session = None
                self._fail_pending("simplex-chat connection lost")

            if self._stopping.is_set():
                break
            await asyncio.sleep(self._reconnect_delay)

    async def _read_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
                continue
            try:
                data = json.loads(msg.data)
            except json.JSONDecodeError:
                continue
            self._dispatch(data)

    def _dispatch(self, data: dict[str, Any]) -> None:
        corr_id = data.get("corrId")
        resp = data.get("resp", {})
        future = self._pending.pop(corr_id, None) if corr_id is not None else None
        if future is not None:
            if not future.done():
                future.set_result(resp)
            return
        # No matching corrId → asynchronous event.
        self._handle_event(_unwrap_event(resp))

    def _handle_event(self, payload: dict[str, Any]) -> None:
        event_type = payload.get("type")
        if event_type == "newChatItems":
            for entry in payload.get("chatItems", []):
                self._emit_message(entry)
        elif event_type == "newChatItem":
            # Legacy singular form.
            self._emit_message(payload.get("chatItem", {}))
        elif event_type in {"contactConnected", "contactRequest", "acceptingContactRequest"}:
            logger.debug(
                "simplex contact event",
                connector_id=self.connector_id,
                event_type=event_type,
            )

    def _emit_message(self, entry: dict[str, Any]) -> None:
        """Normalize one chat item; forward only 1:1 received text messages."""
        chat_info = entry.get("chatInfo", {})
        if chat_info.get("type") != "direct":  # 1:1 only
            return
        contact = chat_info.get("contact", {})
        chat_item = entry.get("chatItem", {})
        # Only inbound messages (skip our own sends echoed back).
        if (chat_item.get("chatDir") or {}).get("type") != "directRcv":
            return
        content = (chat_item.get("content") or {}).get("msgContent") or {}
        if content.get("type") != "text":
            return
        text = (content.get("text") or "").strip()
        if not text:
            return
        contact_id = contact.get("contactId")
        if contact_id is None:
            return
        self.inbound.put_nowait(
            {
                "type": "message",
                "source_id": contact_id,
                "source_name": contact.get("localDisplayName") or str(contact_id),
                "item_id": (chat_item.get("meta") or {}).get("itemId"),
                "text": text,
            }
        )

    def _fail_pending(self, reason: str) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(SimplexError(reason, transient=True))
        self._pending.clear()


class SimplexBotManager:
    """Manages one SimplexConnection per connector_id."""

    def __init__(
        self,
        bots_config: list[BotConfig],
        send_timeout: float,
        reconnect_delay: float,
    ):
        self._conns: dict[str, SimplexConnection] = {}
        for cfg in bots_config:
            self._conns[cfg.connector_id] = SimplexConnection(
                cfg.connector_id,
                cfg.ws_url,
                cfg.user_id,
                send_timeout,
                reconnect_delay,
            )

    def get_client_by_connector_id(self, connector_id: str) -> SimplexConnection:
        conn = self._conns.get(connector_id)
        if conn is None:
            raise KeyError(f"Invalid connector_id: {connector_id}")
        return conn

    async def start_all(self) -> None:
        for conn in self._conns.values():
            await conn.start()

    async def close_sessions(self) -> None:
        for conn in self._conns.values():
            await conn.close()
        logger.debug("SimpleX connections closed")

    @property
    def connections(self) -> dict[str, SimplexConnection]:
        return self._conns
