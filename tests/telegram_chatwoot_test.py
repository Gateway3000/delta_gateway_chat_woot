import asyncio
from typing import Any
from unittest.mock import AsyncMock

import asyncpg
import pytest
from httpx import AsyncClient, ASGITransport

from app.app import app
from app.di import settings


@pytest.mark.order(1)
@pytest.mark.asyncio(loop_scope="session")
async def test_telegram_chatwoot(
    monkeypatch: pytest.MonkeyPatch,
    start_workers: tuple[asyncio.Task[Any], asyncio.Task[Any]],
    get_db_pool: asyncpg.Pool,
) -> None:
    raw_data = {
        "message": {
            "chat": {"first_name": "TestUser", "id": 1234567890, "type": "private"},
            "date": 1763149331,
            "from": {
                "first_name": "TestUser",
                "id": 1234567890,
                "is_bot": False,
                "language_code": "en",
            },
            "message_id": 300,
            "text": "TestText",
        },
        "update_id": 353411705,
    }

    # Mock two methods that depend on external infrastructure: Telegram and Chatwoot
    mock_feed_update = AsyncMock()
    mock_deliver_message = AsyncMock()
    monkeypatch.setattr(
        "aiogram.dispatcher.dispatcher.Dispatcher.feed_update",
        mock_feed_update,
    )
    monkeypatch.setattr(
        "infrastructure.chatwoot_client.cw_client.ChatwootClient.deliver_message",
        mock_deliver_message,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as cl:
        response = await cl.post(
            f"/ingest/incoming/telegram/{settings.bots_config[0].connector_id}/webhook",
            json=raw_data,
        )
        await asyncio.sleep(1)

    async with get_db_pool.acquire() as conn:
        q_to_cw_res = await conn.fetch("SELECT COUNT(*) FROM pgmq.q_to_cw")
        processed_keys_res = await conn.fetchrow("SELECT * FROM public.processed_keys")

    assert response.status_code == 204

    mock_feed_update.assert_called_once()
    mock_deliver_message.assert_called_once()

    # Check that there are no records in the "q_to_cw" table, therefore, the worker deleted the record after
    # successfully processing it
    assert q_to_cw_res[0]["count"] == 0

    # Check that the record was put in the "processed_keys" table
    assert processed_keys_res["key"] == "telegram:tg1:1234567890:300"

    # ========== CHECK THE SECOND CALL WITH THE SAME ARGUMENTS, IT SHOULD BE PROCESSED DIFFERENTLY =========
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as cl:
        response = await cl.post(
            f"/ingest/incoming/telegram/{settings.bots_config[0].connector_id}/webhook",
            json=raw_data,
        )

    # The second call throws IdempotencyKeyAlreadyProcessedError
    assert response.status_code == 200
