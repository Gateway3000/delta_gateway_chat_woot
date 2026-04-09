import asyncio
import contextlib
import json
import random
from typing import Any

import structlog
from opentelemetry.trace import SpanKind

from src.multichannel_gateway.core import FatalError, TransientError
from src.multichannel_gateway.infrastructure import PGMessageQueue
from src.multichannel_gateway.infrastructure.telemetry import (
    build_worker_message_attributes,
    extract_trace_context,
    mark_span_error,
    mark_span_ok,
    set_span_attributes,
    get_tracer,
)

logger = structlog.get_logger(__name__)
tracer = get_tracer(__name__)


class BaseWorker:
    def __init__(
        self,
        mq: PGMessageQueue,
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
        self._worker_name = self.__class__.__name__

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
                    worker=self._worker_name,
                    queue=self._queue_name,
                    count=len(messages),
                )
            return messages
        except Exception as exc:
            logger.error(
                "Queue reading error",
                worker=self._worker_name,
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
            logger.debug(
                "Worker stopped due to timeout",
                queue=self._queue_name,
                timeout=wait_timeout,
            )

    def _on_task_done(self, tsk: asyncio.Task[None]) -> None:
        self._tasks.discard(tsk)
        self._sem.release()
        with contextlib.suppress(asyncio.CancelledError):
            exc = tsk.exception()
            if exc is not None:
                logger.critical(
                    "Worker task failed",
                    worker=self._worker_name,
                    queue=self._queue_name,
                    task_name=tsk.get_name(),
                    error=repr(exc),
                )

    async def _process_messages(self, messages: list[dict[str, Any]]) -> None:
        """Process each message with concurrency control."""
        for msg in messages:
            if self._stopping.is_set():
                logger.info("Stopping flag set, aborting message processing")
                break
            await self._sem.acquire()
            task = asyncio.create_task(
                self._process_wrapper(msg),
                name=f"{self._worker_name}:{self._queue_name}:{msg['msg_id']}",
            )
            self._tasks.add(task)
            task.add_done_callback(self._on_task_done)
            logger.debug(
                "Task created",
                worker=self._worker_name,
                queue=self._queue_name,
                msg_id=msg["msg_id"],
                task_name=task.get_name(),
            )

    async def _finalize_tasks(self) -> None:
        """Await all running tasks on shutdown."""
        logger.warning(
            "Tasks to complete",
            worker=self._worker_name,
            pending_tasks=len(self._tasks),
        )
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _process_wrapper(self, msg: dict[str, Any]) -> None:
        msg_id, attempts, payload, parent_context = self._prepare_message(msg)
        await self._process_message(msg_id, attempts, payload, parent_context)

    def _prepare_message(
        self, msg: dict[str, Any]
    ) -> tuple[int, int, dict[str, Any], Any | None]:
        msg_id = msg["msg_id"]
        attempts = msg.get("read_ct", 0)
        payload = msg["message"]

        try:
            payload_dict = self._decode_payload(payload)
            parent_context, prepared_payload = extract_trace_context(payload_dict)
        except Exception as exc:
            self._mark_message_parse_error(msg_id, attempts, exc)
            raise

        return msg_id, attempts, prepared_payload, parent_context

    @staticmethod
    def _decode_payload(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, str):
            raise ValueError("payload must be a string")

        decoded_payload = json.loads(payload)
        if not isinstance(decoded_payload, dict):
            raise ValueError("payload must decode to a JSON object")
        return decoded_payload

    def _mark_message_parse_error(
        self, msg_id: int, attempts: int, exc: Exception
    ) -> None:
        with tracer.start_as_current_span(
            "worker.message.process", kind=SpanKind.CONSUMER
        ) as span:
            set_span_attributes(
                span,
                build_worker_message_attributes(
                    self._worker_name, self._queue_name, msg_id, attempts
                ),
            )
            mark_span_error(span, exc)

    async def _process_message(
        self,
        msg_id: int,
        attempts: int,
        payload: dict[str, Any],
        parent_context: Any | None,
    ) -> None:
        message_attributes = build_worker_message_attributes(
            self._worker_name,
            self._queue_name,
            msg_id,
            attempts,
            payload,
        )
        read_attributes = {
            **message_attributes,
            "messaging.operation": "receive",
        }

        with tracer.start_as_current_span(
            "worker.queue.read",
            kind=SpanKind.CONSUMER,
            context=parent_context,
        ) as read_span:
            set_span_attributes(read_span, read_attributes)
            read_span.set_attribute(
                "messaging.trace_context.propagated",
                parent_context is not None,
            )

            with tracer.start_as_current_span(
                "worker.message.process", kind=SpanKind.INTERNAL
            ) as span:
                set_span_attributes(span, message_attributes)

                try:
                    outcome, handled_error = await self._handle_with_retries(
                        msg_id, payload, attempts
                    )
                    self._apply_processing_result(
                        span, read_span, outcome, handled_error
                    )
                except Exception as exc:
                    mark_span_error(span, exc)
                    mark_span_error(read_span, exc)
                    raise

    @staticmethod
    def _apply_processing_result(
        span: Any, read_span: Any, outcome: str, handled_error: Exception | None
    ) -> None:
        span.set_attribute("worker.message.outcome", outcome)
        if handled_error is None:
            mark_span_ok(span)
            mark_span_ok(read_span)
            return

        mark_span_error(span, handled_error)
        mark_span_error(read_span, handled_error)

    async def _handle_with_retries(
        self, msg_id: int, payload: dict[str, Any], attempts: int
    ) -> tuple[str, Exception | None]:
        try:
            await self._handle_message(payload)
            logger.debug("Deleting successfully processed message", msg_id=msg_id)
            await self._mq.delete(self._queue_name, msg_id)
            return "deleted", None
        except Exception as exc:
            outcome = await self._handle_error(msg_id, exc, attempts)
            return outcome, exc

    async def _handle_error(self, msg_id: Any, exc: Exception, attempts: int) -> str:
        if isinstance(exc, TransientError):
            max_attempts = exc.max_transient_attempts
            if attempts >= max_attempts:
                logger.error(
                    "Transient error retry limit exceeded, archiving message",
                    msg_id=msg_id,
                    attempts=attempts,
                    queue=self._queue_name,
                    error=repr(exc),
                )
                await self._mq.archive(self._queue_name, msg_id)
                return "archived_transient_exhausted"

            delay = exc.retry_delay_seconds
            logger.warning(
                "Transient error, will retry later",
                msg_id=msg_id,
                delay=delay,
                attempts=attempts,
                queue=self._queue_name,
                error=repr(exc),
            )
            await self._mq.set_vt(self._queue_name, msg_id, delay)
            return "retry_scheduled"

        if isinstance(exc, FatalError):
            logger.error(
                "Fatal error, archiving message",
                msg_id=msg_id,
                error=repr(exc),
            )
            await self._mq.archive(self._queue_name, msg_id)
            return "archived_fatal"

        if isinstance(exc, Exception):
            logger.error(
                "Unknown exception occurred. No VT was set, the message is still visible",
                read_ct_attempts=attempts,
                error=repr(exc),
            )
            if attempts > 10:
                await self._mq.archive(self._queue_name, msg_id)
                return "archived_max_attempts"
        return "left_visible"

    async def _handle_message(self, payload: dict[str, Any]) -> None:
        """
        Process a single message.

        Expected error contract:

        - `TransientError`: schedule a delayed retry through the queue.
        - `FatalError`: archive the message.
        - other exceptions: leave the message to become visible again after VT.
        - success: delete the message from the queue.

        Subclasses may still use narrower local retry around specific external calls,
        for example provider rate limits, but that retry should not wrap the entire
        message handling flow.
        """
        raise NotImplementedError(
            "_handle_message must be implemented by child classes"
        )
