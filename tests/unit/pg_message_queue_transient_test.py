from unittest.mock import AsyncMock, Mock

import pytest

from src.multichannel_gateway.core.exceptions import TransientError
from src.multichannel_gateway.app.services.handlers import _handle_exceptions
from src.multichannel_gateway.infrastructure.pg_message_queue import PGMessageQueue


class TestPGMessageQueueTransientErrors:
    @pytest.mark.asyncio
    async def test_is_already_processed_maps_os_error_to_transient_error(self) -> None:
        conn_manager = Mock()
        conn_manager.get_pg_pool = AsyncMock(
            side_effect=OSError("Connect call failed ('127.0.0.1', 5432)")
        )
        settings = Mock()
        queue = PGMessageQueue(settings=settings, conn_manager=conn_manager)

        with pytest.raises(TransientError) as exc_info:
            await queue.is_already_processed("key-1")

        assert "Postgres temporarily unavailable" in str(exc_info.value)
        assert (
            exc_info.value.retry_delay_seconds == TransientError().retry_delay_seconds
        )

    def test_handle_exceptions_returns_503_for_transient_error(self) -> None:
        span = Mock()
        exc = TransientError("database unavailable", retry_delay_seconds=5)

        response = _handle_exceptions(exc, span, {"channel": "telegram"})

        assert response is not None
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "5"
