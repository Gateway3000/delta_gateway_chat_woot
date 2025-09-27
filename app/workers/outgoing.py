from typing import Any

import structlog
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
)

from app.workers.base import BaseWorker
from core.exceptions import RateLimitError
from core.interfaces.message_queue import IMessageQueue

logger = structlog.get_logger(__name__)


class OutgoingWorker(BaseWorker):
    def __init__(self, mq: IMessageQueue, queue_name: str):
        super().__init__(mq, queue_name)
        self._mq = mq
        self._queue_name = queue_name

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=12, max=60),
        retry=retry_if_exception_type(RateLimitError),
        reraise=True,
    )
    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Contains the logic for processing messages from Chatwoot to Gateway."""
        from app.di import gateways

        channel = str(message.get("channel"))
        logger.debug("Sending message to channel", channel=channel, payload=message)
        gateway = gateways.get_gateway(channel)
        await gateway.send_to_user(message)
        logger.debug("Message successfully sent to channel", channel=channel)
