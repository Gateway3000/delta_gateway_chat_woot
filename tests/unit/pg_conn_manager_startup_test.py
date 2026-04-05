from unittest.mock import AsyncMock, patch

import pytest

from src.multichannel_gateway.core.exceptions import TransientError
from src.multichannel_gateway.infrastructure.pg_conn_manager import ConnManager


class TestConnManagerTransientErrors:
    @pytest.mark.asyncio
    async def test_get_connection_maps_os_error_to_transient_error(self) -> None:
        manager = ConnManager("postgresql://test")

        with patch(
            "src.multichannel_gateway.infrastructure.pg_conn_manager.asyncpg.connect",
            AsyncMock(side_effect=OSError("Connect call failed")),
        ):
            with pytest.raises(TransientError) as exc_info:
                await manager.get_connection("postgresql://test")

        assert "Postgres temporarily unavailable" in str(exc_info.value)
        assert (
            exc_info.value.retry_delay_seconds == TransientError().retry_delay_seconds
        )
