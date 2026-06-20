import asyncio
from typing import Any

import structlog

from channels.signal_channel.sig_bot_manager import SignalBotManager
from channels.signal_channel.sig_routing import SignalRouting
from channels.signal_channel.plugin_settings import SignalSettings
from src.multichannel_gateway.core import (
    IdempotencyKeyAlreadyProcessedError,
    TransientError,
    WrongUpdateTypeError,
)

logger = structlog.get_logger(__name__)


class SignalReceiver:
    """Pulls inbound Signal messages by long-polling signal-cli-rest-api.

    This is the one piece with no analogue in the Telegram/iMessage
    channels: those receive via inbound webhooks hitting
    `/ingest/incoming/...`, but signal-cli-rest-api pushes nothing — it
    exposes `GET /v1/receive/{number}`, which blocks until a message
    arrives (or the server-side timeout elapses) and returns a JSON array,
    *consuming* those messages from signal-cli's queue.

    One polling task runs per connector. Each received envelope is fed
    through the same `channel_to_chatwoot_orchestrator` the webhook handler
    uses, so channel-prefixing, anonymization, the durable `to_cw` queue,
    and Chatwoot delivery all behave identically to the other channels.
    Non-text / non-1:1 envelopes are filtered out by the envelope factory
    (raising WrongUpdateTypeError), which we treat as "skip".
    """

    def __init__(
        self,
        bot_manager: SignalBotManager,
        routing: SignalRouting,
        settings: SignalSettings,
        channel: str = "signal",
    ) -> None:
        self._bots = bot_manager
        self._routing = routing
        self._settings = settings
        self._channel = channel
        self._tasks: list[asyncio.Task[None]] = []
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if self._tasks:
            return
        for connector_id in self._routing.connector_ids:
            task = asyncio.create_task(
                self._poll_connector(connector_id),
                name=f"signal_receiver_{connector_id}",
            )
            self._tasks.append(task)
        logger.info("Signal receiver started", connectors=len(self._tasks))

    async def stop(self) -> None:
        self._stopping.set()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def _poll_connector(self, connector_id: str) -> None:
        client = self._bots.get_client_by_connector_id(connector_id)
        while not self._stopping.is_set():
            try:
                items = await client.receive()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Signal receive failed; backing off",
                    connector_id=connector_id,
                    error=repr(exc),
                )
                await asyncio.sleep(self._settings.receive_error_backoff)
                continue

            if not items:
                await asyncio.sleep(self._settings.receive_poll_delay)
                continue

            for item in items:
                await self._dispatch(connector_id, item)

    async def _dispatch(self, connector_id: str, item: dict[str, Any]) -> None:
        # Lazy import: the orchestrator lives in app wiring, importing it at
        # module load would create a cycle (wiring -> channels -> wiring).
        from src.multichannel_gateway.app.wiring import (
            channel_to_chatwoot_orchestrator,
        )

        item["channel"] = self._channel
        item["connector_id"] = connector_id
        try:
            await channel_to_chatwoot_orchestrator.process(self._channel, item)
        except WrongUpdateTypeError:
            # Not a 1:1 text message (sync/receipt/typing/group/empty) — skip.
            return
        except IdempotencyKeyAlreadyProcessedError:
            # Already enqueued (e.g. a re-delivered envelope) — safe to drop.
            return
        except TransientError as exc:
            # The receive call already consumed this message from signal-cli,
            # so there's nothing to re-poll; log loudly so it isn't silent.
            logger.error(
                "Transient error processing Signal message; message dropped",
                connector_id=connector_id,
                error=repr(exc),
            )
        except Exception as exc:
            logger.error(
                "Failed to process Signal message",
                connector_id=connector_id,
                error=repr(exc),
            )
