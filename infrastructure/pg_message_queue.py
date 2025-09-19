from datetime import datetime, timezone
from typing import Any

import asyncpg

from core.interfaces.message_queue import IMessageQueue


class PGMessageQueue(IMessageQueue):
    def __init__(self, pg_dsn: str):
        self._pg_dsn = pg_dsn
        self._pg_pool: asyncpg.pool.Pool | None = None

    async def get_pg_pool(self) -> asyncpg.pool.Pool:
        if self._pg_pool is None:
            self._pg_pool = await asyncpg.create_pool(
                dsn=self._pg_dsn, min_size=1, max_size=5
            )
        return self._pg_pool

    async def send(self, queue_name: str, payload: str) -> None:
        """
        Sends a message to the PG queue.
        """
        pool = await self.get_pg_pool()
        query = "SELECT pgmq.send($1, $2::jsonb)"

        async with pool.acquire() as conn:
            await conn.execute(query, queue_name, payload)

    async def read(
        self, queue_name: str, vt: int = 30, limit: int = 1
    ) -> list[dict[str, Any]]:
        """
        Reads messages from the queue and makes them invisible for `vt` seconds.
        """
        pool = await self.get_pg_pool()
        query = "SELECT * FROM pgmq.read($1::text, $2::int, $3::int)"
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, queue_name, vt, limit)
            return [dict(r) for r in rows]

    async def delete(self, queue_name: str, msg_id: int) -> None:
        """
        Deletes processed messages from the queue.
        """
        pool = await self.get_pg_pool()
        query = "SELECT pgmq.delete($1::text, $2::bigint)"
        async with pool.acquire() as conn:
            await conn.execute(query, queue_name, msg_id)

    async def archive(self, queue_name: str, msg_id: int) -> None:
        """
        Archives a message from the queue.
        """
        pool = await self.get_pg_pool()
        query = "SELECT pgmq.archive($1::text, $2::bigint)"
        async with pool.acquire() as conn:
            await conn.execute(query, queue_name, msg_id)

    async def is_already_processed(self, key: str) -> bool:
        pool = await self.get_pg_pool()
        query = "SELECT 1 FROM processed_keys WHERE key = $1"

        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, key)
            return row is not None

    async def mark_as_processed(self, key: str) -> None:
        pool = await self.get_pg_pool()
        query = """
            INSERT INTO processed_keys (key, processed_at)
            VALUES ($1, $2)
            ON CONFLICT (key) DO NOTHING
        """

        async with pool.acquire() as conn:
            await conn.execute(query, key, datetime.now(timezone.utc))

    async def close(self) -> None:
        if self._pg_pool is not None:
            await self._pg_pool.close()
            self._pg_pool = None
