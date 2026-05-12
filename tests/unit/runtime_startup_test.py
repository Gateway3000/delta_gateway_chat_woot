from unittest.mock import AsyncMock

import pytest

from src.multichannel_gateway.app.utils.runtime import wait_until_database_ready
from src.multichannel_gateway.core.exceptions import TransientError


class TestStartupDatabaseRetry:
    @pytest.mark.asyncio
    async def test_wait_until_database_ready_retries_on_transient_error(self) -> None:
        pgmq = AsyncMock()
        transient_error = TransientError(
            "db unavailable",
            max_transient_attempts=10,
            retry_delay_seconds=3,
        )
        pgmq.ensure_database_ready = AsyncMock(side_effect=[transient_error, None])

        sleep_mock = AsyncMock()

        import src.multichannel_gateway.app.utils.runtime as runtime_module

        original_sleep = runtime_module.asyncio.sleep
        runtime_module.asyncio.sleep = sleep_mock
        try:
            await wait_until_database_ready(pgmq)
        finally:
            runtime_module.asyncio.sleep = original_sleep

        assert pgmq.ensure_database_ready.await_count == 2
        sleep_mock.assert_awaited_once_with(3)

    @pytest.mark.asyncio
    async def test_wait_until_database_ready_stops_at_transient_error_limit(
        self,
    ) -> None:
        pgmq = AsyncMock()
        transient_error = TransientError(
            "db unavailable",
            max_transient_attempts=2,
            retry_delay_seconds=3,
        )
        pgmq.ensure_database_ready = AsyncMock(
            side_effect=[transient_error, transient_error]
        )

        sleep_mock = AsyncMock()

        import src.multichannel_gateway.app.utils.runtime as runtime_module

        original_sleep = runtime_module.asyncio.sleep
        runtime_module.asyncio.sleep = sleep_mock
        try:
            with pytest.raises(ConnectionError):
                await wait_until_database_ready(pgmq)
        finally:
            runtime_module.asyncio.sleep = original_sleep

        assert pgmq.ensure_database_ready.await_count == 2
        sleep_mock.assert_awaited_once_with(3)
