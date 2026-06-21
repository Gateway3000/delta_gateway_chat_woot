from __future__ import annotations

from uuid import uuid4

from asyncpg import Connection

from src.multichannel_gateway.infrastructure.pg_conn_manager import ConnManager


class IdentityStore:
    def __init__(self, conn_manager: ConnManager) -> None:
        self._conn_manager = conn_manager

    @staticmethod
    async def ensure_table(conn: Connection) -> None:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS identity_mappings (
                channel TEXT NOT NULL,
                external_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (channel, external_id),
                UNIQUE (channel, actor_id)
            );
            """
        )

    async def get_or_create_actor_id(self, channel: str, external_id: str) -> str:
        pool = await self._conn_manager.get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT actor_id
                FROM identity_mappings
                WHERE channel = $1 AND external_id = $2
                """,
                channel,
                external_id,
            )
            if row:
                return str(row["actor_id"])

            actor_id = f"{channel}_{uuid4().hex}"
            await conn.execute(
                """
                INSERT INTO identity_mappings (channel, external_id, actor_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (channel, external_id) DO UPDATE
                    SET actor_id = EXCLUDED.actor_id
                """,
                channel,
                external_id,
                actor_id,
            )
            return actor_id

    async def resolve_external_id(self, channel: str, actor_id: str) -> str:
        pool = await self._conn_manager.get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT external_id
                FROM identity_mappings
                WHERE channel = $1 AND actor_id = $2
                """,
                channel,
                actor_id,
            )
            if row is None:
                raise ValueError(f"Unknown actor_id for channel={channel}")
            return str(row["external_id"])
