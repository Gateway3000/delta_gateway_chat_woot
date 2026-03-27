from typing import Any

import structlog
from opentelemetry.trace import SpanKind
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
)

from multichannel_gateway.core.name_generator import generate_username
from src.multichannel_gateway.app.config import Settings
from src.multichannel_gateway.app.workers.base import BaseWorker
from src.multichannel_gateway.core.interfaces.cw_client import IChatwootClient

from src.multichannel_gateway.infrastructure.registry import GatewayRegistry
from src.multichannel_gateway.core.interfaces.message_queue import IMessageQueue
from src.multichannel_gateway.infrastructure.telemetry.helpers import (
    mark_span_ok,
    set_span_attributes,
)
from src.multichannel_gateway.infrastructure.telemetry.tracing import get_tracer

logger = structlog.get_logger(__name__)
tracer = get_tracer(__name__)


class IncomingWorker(BaseWorker):
    def __init__(
        self,
        settings: Settings,
        mq: IMessageQueue,
        cw_client: IChatwootClient,
        queue_name: str,
        gateways: GatewayRegistry,
    ):
        super().__init__(mq, queue_name)
        self.settings = settings
        self._mq = mq
        self._queue_name = queue_name
        self._cwc = cw_client
        self._gateways = gateways

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=5, max=30),
        reraise=True,
    )
    async def _handle_message(self, message: dict[str, Any]) -> None:
        """
        Contains the logic for processing messages from Gateway to Chatwoot.

        Error handling:
          - Raise `RateLimitError` for HTTP 429 responses.
          - Raise `TransientError` for temporary issues.
          - Raise `FatalError` for non-retryable 4xx responses.
        """
        with tracer.start_as_current_span(
            "incoming_worker.deliver_to_chatwoot", kind=SpanKind.INTERNAL
        ) as span:
            name = generate_username()[0]
            if not self.settings.anonymize_users and message["sender"]["name"]:
                name = message["sender"]["name"]

            tid = message["sender"]["external_id"]
            msg = message["payload"]["text"]
            connector_id = message["connector_id"]
            cw_account_id = message["cw_account_id"]
            channel = message["channel"]
            gw = self._gateways.get_gateway(channel)
            route = gw.get_route_by_connector_id(connector_id)
            cw_inbox_id = route["cw_inbox_id"]

            set_span_attributes(
                span,
                {
                    "channel": channel,
                    "connector_id": connector_id,
                    "cw.account_id": cw_account_id,
                    "cw.inbox_id": cw_inbox_id,
                    "enduser.id": tid,
                },
            )

            await self._cwc.deliver_message(
                account_id=cw_account_id,
                identifier=str(tid),
                inbox_id=int(cw_inbox_id),
                content=msg,
                name=name,
            )
            mark_span_ok(span)
            logger.debug(
                "Incoming message delivered to Chatwoot",
                channel=channel,
                connector_id=connector_id,
                cw_account_id=cw_account_id,
                enduser_id=tid,
            )
