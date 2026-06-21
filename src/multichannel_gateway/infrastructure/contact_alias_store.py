import structlog

from src.multichannel_gateway.infrastructure.pg_conn_manager import ConnManager
from src.multichannel_gateway.infrastructure.postgres_transient import (
    is_transient_postgres_error,
    raise_transient_postgres_error,
)

logger = structlog.get_logger(__name__)


class ContactAliasStore:
    """Manages the contact_aliases table for anonymizing user identifiers sent to Chatwoot.

    Maps (channel, real_id) → opaque UUID alias. The alias is stored as the
    Chatwoot contact identifier so operators never see the real phone/email/user ID.
    """

    def __init__(self, conn_manager: ConnManager) -> None:
        self._conn_manager = conn_manager

    async def ensure_table(self) -> None:
        """Creates the contact_aliases table and index if they do not exist."""
        try:
            pool = await self._conn_manager.get_pg_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS pgmq.contact_aliases (
                        channel      TEXT        NOT NULL,
                        real_id      TEXT        NOT NULL,
                        alias_id     TEXT        NOT NULL DEFAULT gen_random_uuid()::TEXT,
                        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (channel, real_id)
                    );
                """)
                await conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS contact_aliases_alias_idx
                        ON pgmq.contact_aliases (alias_id);
                """)
            logger.debug("contact_aliases table ensured")
        except Exception as exc:
            if is_transient_postgres_error(exc):
                raise_transient_postgres_error(exc, operation="ensure_table")
            raise

    async def get_or_create_alias(self, channel: str, real_id: str) -> str:
        """Returns the alias for (channel, real_id), creating one if it does not exist.

        Also updates last_used_at on every call so TTL-based cleanup stays accurate.
        """
        try:
            pool = await self._conn_manager.get_pg_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO pgmq.contact_aliases (channel, real_id)
                    VALUES ($1, $2)
                    ON CONFLICT (channel, real_id) DO UPDATE
                        SET last_used_at = NOW()
                    RETURNING alias_id
                    """,
                    channel,
                    real_id,
                )
            alias_id: str = row["alias_id"]
            logger.debug("Alias resolved", channel=channel, alias_id=alias_id)
            return alias_id
        except Exception as exc:
            if is_transient_postgres_error(exc):
                raise_transient_postgres_error(
                    exc, operation="get_or_create_alias", channel=channel
                )
            raise

    async def resolve_alias(self, alias_id: str) -> str | None:
        """Returns the real_id for a given alias, or None if the alias is unknown.

        Also updates last_used_at so active conversations are not pruned by cleanup jobs.
        """
        try:
            pool = await self._conn_manager.get_pg_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    UPDATE pgmq.contact_aliases
                    SET last_used_at = NOW()
                    WHERE alias_id = $1
                    RETURNING real_id
                    """,
                    alias_id,
                )
            if row is None:
                logger.warning("Alias not found", alias_id=alias_id)
                return None
            real_id: str = row["real_id"]
            logger.debug("Alias resolved", alias_id=alias_id, real_id=real_id)
            return real_id
        except Exception as exc:
            if is_transient_postgres_error(exc):
                raise_transient_postgres_error(
                    exc, operation="resolve_alias", alias_id=alias_id
                )
            raise
