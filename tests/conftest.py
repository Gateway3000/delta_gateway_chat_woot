import asyncio
from typing import AsyncGenerator, Any

import asyncpg
import pytest_asyncio
from testcontainers.postgres import PostgresContainer

from tests.bootstrap_postgres_for_test import bootstrap_postgres

_TEST_POSTGRES_CONTAINER = bootstrap_postgres()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def postgres_container() -> AsyncGenerator[PostgresContainer | None, None]:
    yield _TEST_POSTGRES_CONTAINER
    if _TEST_POSTGRES_CONTAINER is not None:
        _TEST_POSTGRES_CONTAINER.stop()


from src.multichannel_gateway.app.wiring import (  # noqa: E402
    incoming_worker,
    outgoing_worker,
    pgmq,
    conn_manager,
    registry,
    cw_session_manager,
)

from src.multichannel_gateway.infrastructure import (  # noqa: E402
    ChatwootClient,
)
from telegram.tg_wiring import telegram_channel  # noqa: E402


@pytest_asyncio.fixture(scope="session", autouse=True)
async def register_gateway() -> None:
    registry.register_channel(telegram_channel)


@pytest_asyncio.fixture(scope="session")
async def start_session_and_workers(
    get_db_pool: asyncpg.Pool,
) -> AsyncGenerator[None, None]:
    await cw_session_manager.start()
    incoming_task = asyncio.create_task(incoming_worker.run())
    outgoing_task = asyncio.create_task(outgoing_worker.run())
    yield
    incoming_task.cancel()
    outgoing_task.cancel()
    await asyncio.gather(incoming_task, outgoing_task, return_exceptions=True)
    await cw_session_manager.stop()


@pytest_asyncio.fixture(scope="session")
async def get_db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    await pgmq.ensure_database_ready()
    pool = await conn_manager.get_pg_pool()
    yield pool
    async with pool.acquire() as conn:
        await truncate_all_tables(conn)
    await pgmq.close()


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


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[ChatwootClient, None]:
    started_here = False
    try:
        _ = cw_session_manager.session
    except RuntimeError:
        await cw_session_manager.start()
        started_here = True

    yield ChatwootClient(
        api_access_token="test-token",
        base_url="https://chatwoot.example.com",
        cw_session_manager=cw_session_manager,
    )

    if started_here:
        await cw_session_manager.stop()
