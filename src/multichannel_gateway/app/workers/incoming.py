from typing import Any

import structlog
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
)

from src.multichannel_gateway.app.workers.base import BaseWorker
from src.multichannel_gateway.core.interfaces.cw_client import IChatwootClient

from src.multichannel_gateway.infrastructure.registry import GatewayRegistry
from src.multichannel_gateway.core.interfaces.message_queue import IMessageQueue

logger = structlog.get_logger(__name__)


class IncomingWorker(BaseWorker):
    def __init__(
        self,
        mq: IMessageQueue,
        cw_client: IChatwootClient,
        queue_name: str,
        gateways: GatewayRegistry,
    ):
        super().__init__(mq, queue_name)
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

        tid = message["sender"]["external_id"]
        msg = message["payload"]["text"]
        connector_id = message["connector_id"]
        cw_account_id = message["cw_account_id"]
        channel = message["channel"]
        gw = self._gateways.get_gateway(channel)
        route = gw.get_route_by_connector_id(connector_id)
        cw_inbox_id = route["cw_inbox_id"]
        await self._cwc.deliver_message(cw_account_id, str(tid), int(cw_inbox_id), msg)
        logger.debug(f"[IncomingWorker] Processing: {message}")
