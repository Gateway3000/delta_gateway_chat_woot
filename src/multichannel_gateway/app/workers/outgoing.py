from typing import Any

import structlog
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
)

from src.multichannel_gateway.app.workers.base import BaseWorker

from src.multichannel_gateway.infrastructure.registry import GatewayRegistry
from src.multichannel_gateway.core.exceptions import RateLimitError
from src.multichannel_gateway.core.interfaces.message_queue import IMessageQueue

logger = structlog.get_logger(__name__)


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

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=5, max=30),
        retry=retry_if_exception_type(RateLimitError),
        reraise=True,
    )
    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Contains the logic for processing messages from Chatwoot to Gateway."""

        channel = str(message.get("channel"))
        gateway = self._gateways.get_gateway(channel)
        logger.debug(f"[OutgoingWorker] Processing: {message}")
        delivery_result = await gateway.send_to_user(message)
        logger.debug(
            "Message successfully sent to channel",
            channel=channel,
            delivery_result=delivery_result,
        )
