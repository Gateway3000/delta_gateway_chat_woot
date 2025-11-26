import asyncio
import contextlib
from datetime import datetime, timezone
from typing import Any

import asyncpg
import structlog
import tenacity
from asyncpg import Connection

from app.config import Settings
from core.interfaces.message_queue import IMessageQueue
from infrastructure.pg_conn_manager import ConnManager

logger = structlog.get_logger(__name__)


class PGMessageQueue(IMessageQueue):
    def __init__(self, settings: Settings, conn_manager: ConnManager) -> None:
        self.settings = settings
        self._conn_manager = conn_manager
        self._event = asyncio.Event()

    async def ensure_database_ready(self) -> None:
        db_conn = await self._conn_manager.get_connection(
            self.settings.db_url.rsplit("/", maxsplit=1)[0] + "/postgres"
        )
        await self.ensure_db_exists(db_conn)
        await db_conn.close()
        db_schema_conn = await self._conn_manager.get_connection(self.settings.db_url)
        await self.ensure_extension_and_tables(db_schema_conn)
        await db_schema_conn.close()

    async def ensure_db_exists(self, conn: Connection) -> None:
        """Creates the database if it does not exist"""
        try:
            await conn.execute(f"CREATE DATABASE {self.settings.db_name};")
            logger.debug(f"Database '{self.settings.db_name}' created.")
        except asyncpg.exceptions.DuplicateDatabaseError:
            logger.debug(f"Database '{self.settings.db_name}' already exists.")

    @staticmethod
    async def ensure_extension_and_tables(conn: Connection) -> None:
        # Create the pgmq extension if it doesn't exist
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pgmq;")

        # Create the processed_keys table if it doesn't exist
        await conn.execute("""
                CREATE TABLE IF NOT EXISTS pgmq.processed_keys (
                    key TEXT PRIMARY KEY,
                    processed_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

        # Create queues if they don't exist
        await conn.execute("SELECT pgmq.create('to_cw');")
        await conn.execute("SELECT pgmq.create('from_cw');")

        # Enable insert notifications
        await conn.execute("SELECT pgmq.enable_notify_insert('to_cw');")
        await conn.execute("SELECT pgmq.enable_notify_insert('from_cw');")

        logger.info("Tables and extensions ensured.")

    async def send(self, queue_name: str, payload: str) -> None:
        """Sends a message to the PG queue."""

        pool = await self._conn_manager.get_pg_pool()
        query = "SELECT pgmq.send($1, $2::jsonb)"
        async with pool.acquire() as conn:
            await conn.execute(query, queue_name, payload)
        logger.debug("Message sent", queue=queue_name)

    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=10, max=600),
        retry=tenacity.retry_if_exception_type((OSError, ConnectionError)),
        before_sleep=tenacity.before_sleep_log(logger, 40),
        reraise=True,
    )
    async def read(
        self, queue_name: str, vt: int = 30, message_limit: int = 1
    ) -> list[dict[str, Any]]:
        """Reads messages from the queue and makes them invisible for `vt` seconds."""

        pool = await self._conn_manager.get_pg_pool()
        query = "SELECT * FROM pgmq.read($1::text, $2::int, $3::int)"
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, queue_name, vt, message_limit)
            messages = [dict(r) for r in rows]
        logger.debug("Messages read", queue=queue_name, count=len(messages))
        return messages

    async def delete(self, queue_name: str, msg_id: int) -> None:
        """Deletes processed messages from the queue."""

        pool = await self._conn_manager.get_pg_pool()
        query = "SELECT pgmq.delete($1::text, $2::bigint)"
        async with pool.acquire() as conn:
            await conn.execute(query, queue_name, msg_id)
        logger.debug("Message deleted", queue=queue_name, msg_id=msg_id)

    async def archive(self, queue_name: str, msg_id: int) -> None:
        """Archives a message from the queue."""

        logger.warning("Archiving message", queue=queue_name, msg_id=msg_id)
        pool = await self._conn_manager.get_pg_pool()
        query = "SELECT pgmq.archive($1::text, $2::bigint)"
        async with pool.acquire() as conn:
            await conn.execute(query, queue_name, msg_id)
        logger.debug("Message archived", queue=queue_name, msg_id=msg_id)

    async def set_vt(self, queue_name: str, msg_id: Any, delay_seconds: float) -> None:
        """Updates the visibility timeout (VT) of a message."""

        if delay_seconds <= 0:
            delay_seconds = 1

        vt_seconds = int(delay_seconds)
        logger.debug("Setting new VT", queue=queue_name, msg_id=msg_id, vt=vt_seconds)

        pool = await self._conn_manager.get_pg_pool()
        query = "SELECT pgmq.set_vt($1::text, $2::bigint, $3::int)"
        async with pool.acquire() as conn:
            await conn.execute(query, queue_name, msg_id, vt_seconds)

        logger.debug(
            "VT updated",
            queue=queue_name,
            msg_id=msg_id,
            vt_seconds=vt_seconds,
        )

    async def wait_for_notification(
        self, queue_name: str, timeout: float
    ) -> bool | None:
        """Waits for a notification on a PostgreSQL queue channel within a given timeout.

        Registers a listener on the channel `pgmq.q_<queue_name>.INSERT` and waits
        for a notification. If a notification is received within the timeout, returns True.
        If the timeout expires without receiving a notification, returns False.
        """

        pool = await self._conn_manager.get_pg_pool()
        async with pool.acquire() as conn:
            channel_name = f"pgmq.q_{queue_name}.INSERT"

            def set_event(
                _conn: Connection, _pid: int, _channel: str, _payload: str | None
            ) -> None:
                if _channel == channel_name:
                    self._event.set()

            await conn.add_listener(channel_name, set_event)
            logger.debug(
                "Listener registered",
                queue=queue_name,
                channel=channel_name,
                timeout=timeout,
            )

            try:
                await asyncio.wait_for(self._event.wait(), timeout)
                logger.debug(
                    "The event was triggered",
                    queue=queue_name,
                    channel=channel_name,
                )
                self._event.clear()
                return True
            except asyncio.TimeoutError:
                logger.debug(
                    "No notifications received within timeout",
                    queue=queue_name,
                    channel=channel_name,
                    timeout=timeout,
                )
                return False
            finally:
                with contextlib.suppress(asyncpg.InterfaceError):
                    await conn.remove_listener(channel_name, set_event)
                    logger.debug(
                        "Listener removed",
                        queue=queue_name,
                        channel=channel_name,
                    )

    async def is_already_processed(self, key: str) -> bool:
        pool = await self._conn_manager.get_pg_pool()
        query = "SELECT 1 FROM pgmq.processed_keys WHERE key = $1"

        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, key)
        return row is not None

    async def mark_as_processed(self, key: str) -> None:
        logger.debug("Marking key as processed", key=key)
        pool = await self._conn_manager.get_pg_pool()
        query = """
            INSERT INTO pgmq.processed_keys (key, processed_at)
            VALUES ($1, $2)
            ON CONFLICT (key) DO NOTHING
        """
        async with pool.acquire() as conn:
            await conn.execute(query, key, datetime.now(timezone.utc))
        logger.debug("Key marked as processed", key=key)

    async def close(self) -> None:
        self._event.set()
        await self._conn_manager.close_pg_pool()
