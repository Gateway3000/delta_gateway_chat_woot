import asyncio

import asyncpg
import structlog
from asyncpg import Connection

from src.multichannel_gateway.infrastructure.postgres_transient import (
    is_transient_postgres_error,
    raise_transient_postgres_error,
)

logger = structlog.get_logger(__name__)


class ConnManager:
    def __init__(
        self, pg_dsn: str, min_pool_size: int = 3, max_pool_size: int = 6
    ) -> None:
        self._pg_dsn = pg_dsn
        self._pg_pool = None
        self._pool_init_lock = asyncio.Lock()
        self._pool_closing_lock = asyncio.Lock()
        self._min_pool_size = min_pool_size
        self._max_pool_size = max_pool_size

    # noinspection PyUnresolvedReferences
    async def _init_pg_pool(self) -> asyncpg.pool.Pool:
        async with self._pool_init_lock:
            if self._pg_pool is None:
                try:
                    self._pg_pool = await asyncpg.create_pool(
                        dsn=self._pg_dsn,
                        min_size=self._min_pool_size,
                        max_size=self._max_pool_size,
                    )
                    logger.debug(
                        "Pool has been created",
                        min_size=self._min_pool_size,
                        max_size=self._max_pool_size,
                    )
                except Exception as exc:
                    if is_transient_postgres_error(exc):
                        raise_transient_postgres_error(exc, operation="create_pool")
                    raise
        return self._pg_pool

    async def close_pg_pool(self) -> None:
        async with self._pool_closing_lock:
            if self._pg_pool is not None:
                logger.debug("Closing PG pool")
                await self._pg_pool.close()
                self._pg_pool = None
                logger.debug("PG pool closed")
            else:
                logger.debug("PG pool already closed or not initialized")

    @staticmethod
    async def get_connection(dsn: str) -> Connection:
        try:
            return await asyncpg.connect(dsn)
        except Exception as exc:
            if is_transient_postgres_error(exc):
                raise_transient_postgres_error(exc, operation="connect")
            raise

    async def get_pg_pool(self) -> asyncpg.pool.Pool:
        if self._pg_pool is None:
            await self._init_pg_pool()
        task = asyncio.current_task()
        logger.debug(
            "Pool already exists, reusing...",
            min_size=self._min_pool_size,
            max_size=self._max_pool_size,
            task_name=task.get_name() if task else None,
        )
        return self._pg_pool
