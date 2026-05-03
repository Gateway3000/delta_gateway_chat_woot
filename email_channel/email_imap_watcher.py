import asyncio

import structlog

from email_channel.email_message_processor import EmailMessageProcessor

logger = structlog.get_logger(__name__)


class EmailImapWatcher:
    """Runs a periodic background loop for inbound IMAP polling."""

    def __init__(
        self,
        message_processor: EmailMessageProcessor,
        poll_interval_seconds: float = 5.0,
    ) -> None:
        self._message_processor = message_processor
        self._interval = poll_interval_seconds
        self._stopping = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run_loop(), name="email-imap-watcher")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await self._message_processor.poll_once()
            except Exception as e:
                logger.error(f"Error during IMAP poll: {str(e)}")
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                continue
