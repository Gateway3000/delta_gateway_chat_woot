from typing import Any

import structlog
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.workers.base import BaseWorker
from core.exceptions import RateLimitError
from core.interfaces.message_queue import IMessageQueue

logger = structlog.get_logger(__name__)


class IncomingWorker(BaseWorker):
    def __init__(self, mq: IMessageQueue, queue_name: str):
        super().__init__(mq, queue_name)
        self._mq = mq
        self._queue_name = queue_name

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=5, max=10),
        reraise=True,
    )
    async def _handle_message(self, message: dict[str, Any]) -> None:
        """
        Contains the logic for processing messages from Gateway to Chatwoot.

        In a real application, this includes steps such as normalization,
        route extraction, and a sequence of actions (e.g., search_contact,
        ensure_contact, etc.).

        Error handling:
          - Raise `RateLimitError` for HTTP 429 responses.
          - Raise `TransientError` for temporary issues.
          - Raise `FatalError` for non-retryable 4xx responses.
        """
        # placeholder
        logger.debug(f"[IncomingWorker] Processing: {message}")
        raise RateLimitError()
