import asyncio
from typing import Any

import structlog

from channels.simplex_channel.sx_bot_manager import SimplexBotManager
from channels.simplex_channel.sx_routing import SimplexRouting
from channels.simplex_channel.plugin_settings import SimplexSettings
from src.multichannel_gateway.core import (
    IdempotencyKeyAlreadyProcessedError,
    TransientError,
    WrongUpdateTypeError,
)

logger = structlog.get_logger(__name__)


class SimplexReceiver:
    """Forwards inbound SimpleX messages from the CLI into the gateway.

    The SimpleX connections (owned by the bot manager) push normalized 1:1
    text `message` events onto a per-connector queue. This receiver drains
    those queues — one task per connector — and feeds each event through the
    same `channel_to_chatwoot_orchestrator` the other channels use.
    """

    def __init__(
        self,
        bot_manager: SimplexBotManager,
        routing: SimplexRouting,
        settings: SimplexSettings,
        channel: str = "simplex",
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
                name=f"simplex_receiver_{connector_id}",
            )
            self._tasks.append(task)
        logger.info("SimpleX receiver started", connectors=len(self._tasks))

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
        # Lazy import: the orchestrator lives in app wiring; importing it at
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
                "Transient error processing SimpleX message; message dropped",
                connector_id=connector_id,
                error=repr(exc),
            )
        except Exception as exc:
            logger.error(
                "Failed to process SimpleX message",
                connector_id=connector_id,
                error=repr(exc),
            )
