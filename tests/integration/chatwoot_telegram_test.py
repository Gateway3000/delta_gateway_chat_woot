import asyncio
from typing import Any
from unittest.mock import AsyncMock

import asyncpg
import pytest
from httpx import AsyncClient, ASGITransport

from channels.telegram_channel.tg_wiring import tg_routing, tg_settings
from src.multichannel_gateway.app.app import app
from src.multichannel_gateway.core.interfaces.envelope_factory import IEnvelopeFactory


@pytest.mark.order(2)
@pytest.mark.asyncio(loop_scope="session")
async def test_chatwoot_telegram(
    monkeypatch: pytest.MonkeyPatch,
    start_session_and_workers: tuple[asyncio.Task[Any], asyncio.Task[Any]],
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
            f"/ingest/outgoing/telegram/{tg_settings.bots_config[0].cw_account_id}/webhook",
            json=raw_data,
        )
        await asyncio.sleep(1)

    async with get_db_pool.acquire() as conn:
        q_from_cw_res = await conn.fetch("SELECT COUNT(*) FROM pgmq.q_from_cw")
        # Get the processed key for this specific test case
        last_processed_key_res = await conn.fetchrow(
            "SELECT * FROM pgmq.processed_keys WHERE key LIKE 'chatwoot->telegram:%' ORDER BY key DESC LIMIT 1"
        )

    assert response.status_code == 204
    mock_send_message.assert_called_once()

    # Check that there are no records in the "q_to_cw" table, therefore, the worker deleted the record after
    # successfully processing it
    assert q_from_cw_res[0]["count"] == 0

    # Check that the record was put in the "processed_keys" table
    # Compute expected key using the same logic as IEnvelopeFactory
    route = tg_routing.get_route_by_inbox_id("18")
    expected_key = IEnvelopeFactory.build_idempotency_key(
        direction="chatwoot->telegram",
        connector_id=route["connector_id"],
        external_id="123321",
        message_id="60538",
        bot_token_suffix=route["bot_token"][-5:],
    )
    stored_key = last_processed_key_res["key"]
    assert stored_key == expected_key

    # ========== CHECK THE SECOND CALL WITH THE SAME ARGUMENTS, IT SHOULD BE PROCESSED DIFFERENTLY =========
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as cl:
        response = await cl.post(
            f"/ingest/outgoing/telegram/{tg_settings.bots_config[0].cw_account_id}/webhook",
            json=raw_data,
        )

    # The second call throws IdempotencyKeyAlreadyProcessedError
    assert response.status_code == 200


class _Msg:
    def __init__(self, message_id: int):
        self.message_id = message_id


@pytest.mark.order(4)
@pytest.mark.asyncio(loop_scope="session")
async def test_chatwoot_telegram_attachment(
    monkeypatch: pytest.MonkeyPatch,
    start_session_and_workers: tuple[asyncio.Task[Any], asyncio.Task[Any]],
) -> None:
    raw_data = {
        "inbox": {"id": "18"},
        "cw_account_id": "3",
        "conversation": {
            "messages": [{"id": "60539"}],
            "meta": {"sender": {"identifier": "123321"}},
        },
        "content": "",
        "attachments": [
            {
                "file_type": "image",
                "data_url": "https://example.com/image.jpg",
            }
        ],
        "message_type": "outgoing",
    }

    mock_send_message = AsyncMock(return_value=_Msg(901))
    mock_send_photo = AsyncMock(return_value=_Msg(902))

    monkeypatch.setattr("aiogram.client.bot.Bot.send_message", mock_send_message)
    monkeypatch.setattr("aiogram.client.bot.Bot.send_photo", mock_send_photo)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as cl:
        response = await cl.post(
            f"/ingest/outgoing/telegram/{tg_settings.bots_config[0].cw_account_id}/webhook",
            json=raw_data,
        )
        await asyncio.sleep(1)

    assert response.status_code == 204
    mock_send_message.assert_not_called()
    mock_send_photo.assert_called_once()
