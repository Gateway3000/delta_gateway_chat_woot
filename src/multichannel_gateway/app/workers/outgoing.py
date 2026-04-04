from typing import Any

import structlog
from opentelemetry.trace import SpanKind

from src.multichannel_gateway.app.workers.base import BaseWorker

from src.multichannel_gateway.infrastructure.registry import GatewayRegistry
from src.multichannel_gateway.core.exceptions import RateLimitError, TransientError
from src.multichannel_gateway.core.interfaces.message_queue import IMessageQueue
from src.multichannel_gateway.infrastructure.telemetry.helpers import (
    mark_span_ok,
    set_span_attributes,
)
from src.multichannel_gateway.infrastructure.telemetry.tracing import get_tracer

logger = structlog.get_logger(__name__)
tracer = get_tracer(__name__)


class OutgoingWorker(BaseWorker):
    def __init__(
        self,
        mq: IMessageQueue,
        queue_name: str,
        gateways: GatewayRegistry,
    ):
        super().__init__(mq, queue_name)
        self._mq = mq
        self._queue_name = queue_name
        self._gateways = gateways

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Contains the logic for processing messages from Chatwoot to Gateway."""
        with tracer.start_as_current_span(
            "outgoing_worker.send_to_channel", kind=SpanKind.INTERNAL
        ) as span:
            channel = str(message.get("channel"))
            gateway = self._gateways.get_gateway(channel)

            set_span_attributes(
                span,
                {
                    "channel": channel,
                    "connector_id": message.get("connector_id"),
                    "cw.account_id": message.get("cw_account_id"),
                },
            )

            try:
                delivery_result = await gateway.send_to_user(message)
            except RateLimitError as exc:
                raise TransientError(
                    f"Gateway rate limited delivery: {exc}",
                    retry_delay_seconds=int(exc.retry_after_seconds),
                ) from exc

            mark_span_ok(span)
            logger.debug(
                "Message successfully sent to channel",
                channel=channel,
                connector_id=message.get("connector_id"),
                external_id=delivery_result.external_id,
            )
