import asyncio
import json
import random
from typing import Any

import structlog

from src.multichannel_gateway.core.exceptions import TransientError, FatalError
from src.multichannel_gateway.core.interfaces.message_queue import IMessageQueue

logger = structlog.get_logger(__name__)


class BaseWorker:
    def __init__(
        self,
        mq: IMessageQueue,
        queue_name: str,
        vt_seconds: int = 30,
        read_timeout: float = 10,
        message_limit: int = 1,
    ):
        self._mq = mq
        self._queue_name = queue_name
        self._vt = vt_seconds
        self._read_to = read_timeout
        self._message_limit = message_limit

        self._sem = asyncio.Semaphore(message_limit)
        self._stopping = asyncio.Event()
        self._tasks: set[asyncio.Task[None]] = set()

    async def stop(self) -> None:
        """Request the worker to stop and wait for all tasks to complete."""
        self._stopping.set()
        await self._mq.close()

    async def run(self) -> None:
        try:
            while not self._stopping.is_set():
                messages = await self._safe_read_queue()
                if not messages:
                    await self._handle_no_messages()
                    continue

                await self._process_messages(messages)

            if task := asyncio.current_task():
                logger.debug("Worker is stopping...", task_name=task.get_name())
            else:
                logger.debug("No task to stop")
        except Exception as exc:
            logger.critical(
                "Unknown error occurred", queue=self._queue_name, error=repr(exc)
            )
            raise
        finally:
            logger.warning("Finalizing...")
            await self._finalize_tasks()

    async def _safe_read_queue(self) -> list[dict[str, Any]]:
        """Read messages from queue with error handling."""
        try:
            messages = await self._mq.read(
                self._queue_name,
                vt=self._vt,
                message_limit=self._message_limit,
            )
            if messages:
                logger.debug(
                    "Messages received",
                    queue=self._queue_name,
                    count=len(messages),
                )
            return messages
        except Exception as exc:
            logger.error(
                "Queue reading error",
                queue=self._queue_name,
                error=repr(exc),
            )
            await asyncio.sleep(self._read_to)
            return []

    async def _handle_no_messages(self) -> None:
        """Handle empty queue case (wait for notification)."""
        logger.debug("Worker is waiting for messages...", queue=self._queue_name)
        wait_timeout = random.randint(290, 310)
        res = await self._mq.wait_for_notification(
            self._queue_name, timeout=wait_timeout
        )
        if res is False:
            logger.info(
                "Worker stopped due to timeout",
                queue=self._queue_name,
                timeout=wait_timeout,
            )

    def _on_task_done(self, tsk: asyncio.Task[None]) -> None:
        self._tasks.discard(tsk)
        self._sem.release()

    async def _process_messages(self, messages: list[dict[str, Any]]) -> None:
        """Process each message with concurrency control."""
        for msg in messages:
            if self._stopping.is_set():
                logger.info("Stopping flag set, aborting message processing")
                break
            await self._sem.acquire()
            task = asyncio.create_task(self._process_wrapper(msg))
            self._tasks.add(task)
            task.add_done_callback(self._on_task_done)
            logger.debug("Task created")

    async def _finalize_tasks(self) -> None:
        """Await all running tasks on shutdown."""
        logger.warning(f"Tasks to complete: {len(self._tasks)}")
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _process_wrapper(self, msg: dict[str, Any]) -> None:
        msg_id = msg["msg_id"]
        payload = msg["message"]
        attempts = msg.get("read_ct", 0)

        if isinstance(payload, str):
            payload = json.loads(payload)
        else:
            raise ValueError("payload must be a string")

        await self._handle_with_retries(msg_id, payload, attempts)

    async def _handle_with_retries(
        self, msg_id: int, payload: dict[str, Any], attempts: int
    ) -> None:
        try:
            await self._handle_message(payload)
            logger.debug("Deleting successfully processed message", msg_id=msg_id)
            await self._mq.delete(self._queue_name, msg_id)
        except Exception as exc:
            await self._handle_error(msg_id, exc, attempts)

    async def _handle_error(self, msg_id: Any, exc: Exception, attempts: int) -> None:
        if isinstance(exc, TransientError):
            delay = getattr(exc, "retry_after", 5)
            logger.warning(
                "Transient error, will retry later",
                msg_id=msg_id,
                delay=delay,
                queue=self._queue_name,
                error=repr(exc),
            )
            return await self._mq.set_vt(self._queue_name, msg_id, delay)

        if isinstance(exc, FatalError):
            logger.error(
                "Fatal error, archiving message",
                msg_id=msg_id,
                error=repr(exc),
            )
            return await self._mq.archive(self._queue_name, msg_id)

        if isinstance(exc, Exception):
            logger.error(
                "Unknown exception occurred. No VT was set, the message is still visible",
                read_ct_attempts=attempts,
                error=repr(exc),
            )
            if attempts > 10:
                return await self._mq.archive(self._queue_name, msg_id)
        return None

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """
        Implements the retry policy for message handling:

        - RateLimitError / TransientError: compute a new VT and exit
          (the message will become visible later).
        - FatalError: re-raise the exception so the message gets archived.
        - Success: delete the message from the queue.
        """
        raise NotImplementedError(
            "_handle_message must be implemented by child classes"
        )
