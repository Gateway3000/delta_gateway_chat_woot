import asyncio
import os
from pathlib import Path
from typing import AsyncGenerator, Any

import asyncpg
import pytest_asyncio
from dotenv import dotenv_values

from src.multichannel_gateway.app.wiring import (
    incoming_worker,
    outgoing_worker,
    pgmq,
    conn_manager,
    registry,
    cw_session_manager,
)
from src.multichannel_gateway.infrastructure.chatwoot_client.cw_client import (
    ChatwootClient,
)
from telegram.tg_wiring import telegram_channel


def _assert_test_database_environment() -> None:
    test_env_path = Path(__file__).resolve().parent.parent / ".test.env"
    expected_db_name = dotenv_values(test_env_path).get("DB_NAME")
    actual_db_name = os.environ.get("DB_NAME")

    if not expected_db_name:
        raise RuntimeError(f"DB_NAME is missing in {test_env_path}")

    if actual_db_name != expected_db_name:
        raise RuntimeError(
            "Unsafe test database configuration: "
            f"expected DB_NAME={expected_db_name!r} from {test_env_path.name}, "
            f"got DB_NAME={actual_db_name!r}. "
            "Refusing to start tests to avoid touching a non-test database."
        )


_assert_test_database_environment()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def register_gateway() -> None:
    registry.register_gateway(telegram_channel)


@pytest_asyncio.fixture(scope="session")
async def start_session_and_workers() -> None:
    await cw_session_manager.start()
    asyncio.create_task(incoming_worker.run())
    asyncio.create_task(outgoing_worker.run())


@pytest_asyncio.fixture(autouse=True, scope="session")
async def get_db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    await pgmq.ensure_database_ready()
    pool = await conn_manager.get_pg_pool()
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
