import asyncio
from typing import AsyncGenerator, Any

import asyncpg
import pytest_asyncio
import structlog

from app.di import incoming_worker, outgoing_worker, pgmq

logger = structlog.get_logger(__name__)


@pytest_asyncio.fixture(scope="session")
async def start_workers() -> None:
    asyncio.create_task(incoming_worker.run())
    asyncio.create_task(outgoing_worker.run())


@pytest_asyncio.fixture(autouse=True, scope="session")
async def get_db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    pool = await pgmq.get_pg_pool()
    yield pool
    async with pool.acquire() as conn:
        await truncate_all_tables(conn)


async def truncate_all_tables(conn: Any) -> None:
    tables = await conn.fetch("""
                              SELECT table_schema, table_name
                              FROM information_schema.tables
                              WHERE table_type = 'BASE TABLE'
                                AND table_schema NOT IN ('information_schema', 'pg_catalog')
                              """)

    for table in tables:
        schema = table["table_schema"]
        table_name = table["table_name"]
        await conn.execute(
            f"TRUNCATE TABLE {schema}.{table_name} RESTART IDENTITY CASCADE;"
        )
