import asyncio
from typing import Any
from unittest.mock import AsyncMock

import asyncpg
import pytest
from httpx import AsyncClient, ASGITransport

from src.multichannel_gateway.app.app import app
from src.multichannel_gateway.app.di import settings


@pytest.mark.order(2)
@pytest.mark.asyncio(loop_scope="session")
async def test_chatwoot_telegram(
    monkeypatch: pytest.MonkeyPatch,
    start_workers: tuple[asyncio.Task[Any], asyncio.Task[Any]],
    get_db_pool: asyncpg.Pool,
) -> None:
    raw_data = {
        "inbox": {"id": "18"},
        "cw_account_id": "3",
        "conversation": {
            "messages": [{"id": "60538"}],
            "meta": {"sender": {"identifier": "123321"}},
        },
        "content": "Test message from Chatwoot!",
        "message_type": "outgoing",
    }

    mock_send_message = AsyncMock()

    monkeypatch.setattr("aiogram.client.bot.Bot.send_message", mock_send_message)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as cl:
        response = await cl.post(
            f"/ingest/outgoing/telegram/{settings.bots_config[0].cw_account_id}/webhook",
            json=raw_data,
        )
        await asyncio.sleep(1)

    async with get_db_pool.acquire() as conn:
        q_from_cw_res = await conn.fetch("SELECT COUNT(*) FROM pgmq.q_from_cw")
        last_processed_key_res = await conn.fetchrow(
            "SELECT * FROM pgmq.processed_keys ORDER BY key DESC LIMIT 1"
        )

    assert response.status_code == 204
    mock_send_message.assert_called_once()

    # Check that there are no records in the "q_to_cw" table, therefore, the worker deleted the record after
    # successfully processing it
    assert q_from_cw_res[0]["count"] == 0

    # Check that the record was put in the "processed_keys" table
    assert last_processed_key_res["key"] == "telegram:tg2:123321:60538"

    # ========== CHECK THE SECOND CALL WITH THE SAME ARGUMENTS, IT SHOULD BE PROCESSED DIFFERENTLY =========
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as cl:
        response = await cl.post(
            f"/ingest/outgoing/telegram/{settings.bots_config[0].cw_account_id}/webhook",
            json=raw_data,
        )

    # The second call throws IdempotencyKeyAlreadyProcessedError
    assert response.status_code == 200
