from unittest.mock import AsyncMock

import pytest

from src.multichannel_gateway.app.workers.base import BaseWorker
from src.multichannel_gateway.core.exceptions import TransientError


class DummyWorker(BaseWorker): ...


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
