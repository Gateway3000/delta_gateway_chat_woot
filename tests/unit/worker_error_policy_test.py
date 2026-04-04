from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock

import pytest

from src.multichannel_gateway.app.workers.base import BaseWorker
from src.multichannel_gateway.core.exceptions import FatalError, TransientError


class DummyWorker(BaseWorker):
    def __init__(self, mq: AsyncMock, queue_name: str) -> None:
        super().__init__(mq, queue_name)
        self.handle_message_calls = 0
        self.handle_message_hook: Callable[[dict[str, object]], Awaitable[None]] = (
            self._noop_handle_message
        )

    async def _handle_message(self, message: dict[str, object]) -> None:
        self.handle_message_calls += 1
        await self.handle_message_hook(message)

    @staticmethod
    async def _noop_handle_message(_: dict[str, object]) -> None:
        return None


class TestWorkerErrorPolicy:
    @pytest.mark.asyncio
    async def test_transient_error_uses_default_delay(self) -> None:
        mq = AsyncMock()
        worker = DummyWorker(mq, "test_queue")

        transient_error = TransientError("temporary failure")
        outcome = await worker._handle_error(
            msg_id=42,
            exc=transient_error,
            attempts=1,
        )

        assert outcome == "retry_scheduled"
        mq.set_vt.assert_awaited_once_with(
            "test_queue",
            42,
            transient_error.retry_delay_seconds,
        )
        mq.archive.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_transient_error_is_archived_after_retry_limit(self) -> None:
        mq = AsyncMock()
        worker = DummyWorker(mq, "test_queue")

        transient_error = TransientError("temporary failure")
        outcome = await worker._handle_error(
            msg_id=42,
            exc=transient_error,
            attempts=transient_error.max_transient_attempts,
        )

        assert outcome == "archived_transient_exhausted"
        mq.archive.assert_awaited_once_with("test_queue", 42)
        mq.set_vt.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_success_deletes_message(self) -> None:
        mq = AsyncMock()
        worker = DummyWorker(mq, "test_queue")
        payload = {"payload": {"attachments": [{"temp_file_path": "tmp.bin"}]}}

        outcome, handled_error = await worker._handle_with_retries(
            msg_id=42,
            payload=payload,
            attempts=1,
        )

        assert outcome == "deleted"
        assert handled_error is None
        mq.delete.assert_awaited_once_with("test_queue", 42)

    @pytest.mark.asyncio
    async def test_fatal_error_archives_message(self) -> None:
        mq = AsyncMock()
        worker = DummyWorker(mq, "test_queue")
        payload = {"payload": {"attachments": [{"temp_file_path": "tmp.bin"}]}}

        async def _raise_fatal(_: dict[str, object]) -> None:
            raise FatalError("fatal")

        worker.handle_message_hook = _raise_fatal

        outcome, handled_error = await worker._handle_with_retries(
            msg_id=42,
            payload=payload,
            attempts=1,
        )

        assert outcome == "archived_fatal"
        assert isinstance(handled_error, FatalError)
        mq.archive.assert_awaited_once_with("test_queue", 42)

    @pytest.mark.asyncio
    async def test_transient_error_schedules_retry(self) -> None:
        mq = AsyncMock()
        worker = DummyWorker(mq, "test_queue")
        payload = {"payload": {"attachments": [{"temp_file_path": "tmp.bin"}]}}

        async def _raise_transient(_: dict[str, object]) -> None:
            raise TransientError("temporary")

        worker.handle_message_hook = _raise_transient

        outcome, handled_error = await worker._handle_with_retries(
            msg_id=42,
            payload=payload,
            attempts=1,
        )

        assert outcome == "retry_scheduled"
        assert isinstance(handled_error, TransientError)
        mq.set_vt.assert_awaited_once()
