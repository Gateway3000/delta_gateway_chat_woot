from __future__ import annotations

import asyncio
import json
from collections import deque
from typing import Any

import structlog

from channels.signal_channel.plugin_settings import BotConfig

logger = structlog.get_logger(__name__)

# The bridge delivers attachments inline as base64 on a single NDJSON line, so
# a line can be much larger than asyncio's default 64 KiB readline limit. A
# ~100 MiB Signal attachment (the platform max) becomes ~137 MiB of base64, so
# the stream limit must comfortably exceed that or `readline()` aborts the
# connection with "Separator is found, but chunk is longer than limit".
_READ_LIMIT = 160 * 1024 * 1024


class SignalBridgeError(Exception):
    """A failure talking to the signal-bridge daemon.

    `transient` distinguishes a recoverable problem (connection dropped,
    timeout) — which the transport maps to a retryable TransientError — from
    a permanent one (the bridge reported the send itself failed).
    """

    def __init__(self, message: str, *, transient: bool = False):
        self.transient = transient
        super().__init__(message)


class SignalBridgeConnection:
    """A persistent TCP client for one signal-bridge instance.

    The bridge serves a newline-delimited JSON protocol: it streams event
    objects to us (incoming messages, lifecycle, send results) and accepts
    one send command per line. This class keeps a single connection alive
    (reconnecting on drop), pushes incoming `message` events onto `inbound`
    for the receiver to consume, and correlates `send_result` replies to
    `send()` callers in FIFO order — which is sound because sends are
    serialized and the bridge replies to each command in order.
    """

    def __init__(
        self,
        connector_id: str,
        host: str,
        port: int,
        send_timeout: float,
        reconnect_delay: float,
    ):
        self.connector_id = connector_id
        self.host = host
        self.port = port
        self._send_timeout = send_timeout
        self._reconnect_delay = reconnect_delay

        self.inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._pending: deque[asyncio.Future[dict[str, Any]]] = deque()
        self._send_lock = asyncio.Lock()
        self._writer: asyncio.StreamWriter | None = None
        self._connected = asyncio.Event()
        self._stopping = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(
                self._run(), name=f"signal_bridge_{self.connector_id}"
            )

    async def close(self) -> None:
        self._stopping.set()
        if self._writer is not None:
            self._writer.close()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def send(
        self,
        recipient: str,
        message: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Send one message and await the bridge's `send_result`.

        `attachments` is an optional list of `{data, content_type, filename}`
        dicts where `data` is the base64-encoded file contents; the bridge
        uploads them to Signal's CDN and links them into the message.
        """
        async with self._send_lock:
            if self._writer is None or not self._connected.is_set():
                raise SignalBridgeError(
                    "not connected to signal-bridge", transient=True
                )

            future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
            self._pending.append(future)

            command: dict[str, Any] = {"recipient": recipient, "message": message}
            if attachments:
                command["attachments"] = attachments
            payload = json.dumps(command) + "\n"
            try:
                self._writer.write(payload.encode("utf-8"))
                await self._writer.drain()
            except (OSError, RuntimeError) as exc:
                self._discard_pending(future)
                raise SignalBridgeError(
                    f"failed to write to signal-bridge: {exc!r}", transient=True
                ) from exc

            try:
                return await asyncio.wait_for(future, timeout=self._send_timeout)
            except asyncio.TimeoutError as exc:
                self._discard_pending(future)
                raise SignalBridgeError(
                    "timed out waiting for signal-bridge send result", transient=True
                ) from exc

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                reader, writer = await asyncio.open_connection(
                    self.host, self.port, limit=_READ_LIMIT
                )
                self._writer = writer
                self._connected.set()
                logger.info(
                    "Connected to signal-bridge",
                    connector_id=self.connector_id,
                    host=self.host,
                    port=self.port,
                )
                await self._read_loop(reader)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "signal-bridge connection error",
                    connector_id=self.connector_id,
                    error=repr(exc),
                )
            finally:
                self._connected.clear()
                self._writer = None
                self._fail_pending("signal-bridge connection lost")

            if self._stopping.is_set():
                break
            await asyncio.sleep(self._reconnect_delay)

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        while not self._stopping.is_set():
            line = await reader.readline()
            if not line:
                break  # EOF — connection closed by the bridge
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.warning(
                    "signal-bridge sent invalid JSON",
                    connector_id=self.connector_id,
                    line=line[:200],
                )
                continue
            self._handle_event(event)

    def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "message":
            self.inbound.put_nowait(event)
        elif event_type == "send_result":
            self._resolve_pending(event)
        elif event_type == "error":
            logger.warning(
                "signal-bridge error event",
                connector_id=self.connector_id,
                error=event.get("error"),
            )
        else:  # linked, ready, queue_empty, ...
            logger.debug(
                "signal-bridge event",
                connector_id=self.connector_id,
                event_type=event_type,
            )

    def _resolve_pending(self, event: dict[str, Any]) -> None:
        if self._pending:
            future = self._pending.popleft()
            if not future.done():
                future.set_result(event)

    def _fail_pending(self, reason: str) -> None:
        while self._pending:
            future = self._pending.popleft()
            if not future.done():
                future.set_exception(SignalBridgeError(reason, transient=True))

    def _discard_pending(self, future: asyncio.Future[dict[str, Any]]) -> None:
        try:
            self._pending.remove(future)
        except ValueError:
            pass


class SignalBotManager:
    """Manages one SignalBridgeConnection per connector_id."""

    def __init__(
        self,
        bots_config: list[BotConfig],
        send_timeout: float,
        reconnect_delay: float,
    ):
        self._conns: dict[str, SignalBridgeConnection] = {}
        for cfg in bots_config:
            self._conns[cfg.connector_id] = SignalBridgeConnection(
                cfg.connector_id,
                cfg.host,
                cfg.port,
                send_timeout,
                reconnect_delay,
            )

    def get_client_by_connector_id(self, connector_id: str) -> SignalBridgeConnection:
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
        logger.debug("Signal bridge connections closed")

    @property
    def connections(self) -> dict[str, SignalBridgeConnection]:
        return self._conns
