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
    """Forwards inbound Signal messages from the bridge into the gateway.

    The signal-bridge connections (owned by the bot manager) stream incoming
    `message` events onto a per-connector queue. This receiver drains those
    queues — one task per connector — and feeds each event through the same
    `channel_to_chatwoot_orchestrator` the other channels' webhook handlers
    use, so channel-prefixing, anonymization, the durable `to_cw` queue, and
    Chatwoot delivery all behave identically.
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
                self._drain_connector(connector_id),
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

    async def _drain_connector(self, connector_id: str) -> None:
        conn = self._bots.get_client_by_connector_id(connector_id)
        while not self._stopping.is_set():
            item = await conn.inbound.get()
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
            return
        except IdempotencyKeyAlreadyProcessedError:
            return
        except TransientError as exc:
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
