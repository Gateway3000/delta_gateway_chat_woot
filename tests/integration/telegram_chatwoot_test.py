import asyncio
from typing import Any
from unittest.mock import ANY, AsyncMock

import asyncpg
import pytest
from httpx import AsyncClient, ASGITransport

from src.multichannel_gateway.app.app import app
from src.multichannel_gateway.core.base_envelope_factory import BaseEnvelopeFactory
from telegram.tg_wiring import tg_routing, tg_settings


def _assert_delivery_confirmation_sent(mock_send_message: AsyncMock) -> None:
    assert mock_send_message.await_count >= 1


@pytest.mark.order(1)
@pytest.mark.asyncio(loop_scope="session")
async def test_telegram_chatwoot(
    monkeypatch: pytest.MonkeyPatch,
    start_session_and_workers: tuple[asyncio.Task[Any], asyncio.Task[Any]],
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

    mock_send_message = AsyncMock()
    mock_deliver_message = AsyncMock()
    monkeypatch.setattr("aiogram.client.bot.Bot.send_message", mock_send_message)
    monkeypatch.setattr(
        "src.multichannel_gateway.infrastructure.chatwoot_client.cw_client.ChatwootClient.deliver_channel_to_chatwoot_message",
        mock_deliver_message,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as cl:
        response = await cl.post(
            f"/ingest/incoming/telegram/{tg_settings.bots_config[0].connector_id}/webhook",
            json=raw_data,
        )
        await asyncio.sleep(1)

    async with get_db_pool.acquire() as conn:
        q_to_cw_res = await conn.fetch("SELECT COUNT(*) FROM pgmq.q_to_cw")
        processed_keys_res = await conn.fetchrow("SELECT * FROM pgmq.processed_keys")

    assert response.status_code == 204
    _assert_delivery_confirmation_sent(mock_send_message)
    mock_deliver_message.assert_called_once()

    # Check that there are no records in the "q_to_cw" table, therefore, the worker deleted the record after
    # successfully processing it
    assert q_to_cw_res[0]["count"] == 0

    # Check that the record was put in the "processed_keys" table
    route = tg_routing.get_route_by_connector_id("tg1")
    expected_key = BaseEnvelopeFactory._build_idempotency_key(
        direction="telegram->chatwoot",
        connector_id="tg1",
        external_id="1234567890",
        message_id="300",
        bot_token_suffix=route["bot_token"][-5:],
    )
    assert processed_keys_res["key"] == expected_key

    # ========== CHECK THE SECOND CALL WITH THE SAME ARGUMENTS, IT SHOULD BE PROCESSED DIFFERENTLY =========
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as cl:
        response = await cl.post(
            f"/ingest/incoming/telegram/{tg_settings.bots_config[0].connector_id}/webhook",
            json=raw_data,
        )

    # The second call throws IdempotencyKeyAlreadyProcessedError
    assert response.status_code == 200


@pytest.mark.order(3)
@pytest.mark.asyncio(loop_scope="session")
async def test_telegram_chatwoot_attachment(
    monkeypatch: pytest.MonkeyPatch,
    start_session_and_workers: tuple[asyncio.Task[Any], asyncio.Task[Any]],
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
            "message_id": 301,
            "caption": "Photo caption",
            "photo": [
                {
                    "file_id": "small_file",
                    "file_unique_id": "small_uid",
                    "file_size": 111,
                    "width": 100,
                    "height": 100,
                },
                {
                    "file_id": "large_file",
                    "file_unique_id": "large_uid",
                    "file_size": 222,
                    "width": 800,
                    "height": 600,
                },
            ],
        },
        "update_id": 353411706,
    }

    mock_send_message = AsyncMock()
    mock_deliver_message = AsyncMock()
    mock_notify = AsyncMock()
    mock_download = AsyncMock(return_value=b"fake-image-bytes")
    monkeypatch.setattr("aiogram.client.bot.Bot.send_message", mock_send_message)
    monkeypatch.setattr(
        "src.multichannel_gateway.infrastructure.chatwoot_client.cw_client.ChatwootClient.deliver_channel_to_chatwoot_message",
        mock_deliver_message,
    )
    monkeypatch.setattr(
        "telegram.tg_attachments.download_telegram_attachment",
        mock_download,
    )
    monkeypatch.setattr(
        "telegram.tg_attachments.notify_telegram_user",
        mock_notify,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as cl:
        response = await cl.post(
            f"/ingest/incoming/telegram/{tg_settings.bots_config[0].connector_id}/webhook",
            json=raw_data,
        )
        await asyncio.sleep(1)

    assert response.status_code == 204
    _assert_delivery_confirmation_sent(mock_send_message)
    mock_download.assert_called_once_with(
        ANY, tg_settings.bots_config[0].connector_id, "large_file"
    )
    mock_notify.assert_not_called()

    attachments = mock_deliver_message.call_args.kwargs["attachments"]
    assert len(attachments) == 1
    assert attachments[0]["kind"] == "base64"
    assert attachments[0]["filename"] == "photo.jpg"
    assert attachments[0]["mime_type"] == "image/jpeg"
    assert attachments[0]["file_type"] == "image"
    assert attachments[0]["data_encoding"] == "base64"
    assert "data" in attachments[0]


@pytest.mark.order(5)
@pytest.mark.asyncio(loop_scope="session")
async def test_telegram_chatwoot_attachment_oversize_notifies_user(
    monkeypatch: pytest.MonkeyPatch,
    start_session_and_workers: tuple[asyncio.Task[Any], asyncio.Task[Any]],
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
            "message_id": 302,
            "text": "Big file incoming",
            "document": {
                "file_id": "doc_big",
                "file_unique_id": "doc_big_uid",
                "file_name": "big.bin",
                "mime_type": "application/octet-stream",
                "file_size": 999 * 1024 * 1024,
            },
        },
        "update_id": 353411707,
    }

    mock_send_message = AsyncMock()
    mock_deliver_message = AsyncMock()
    mock_notify = AsyncMock()
    mock_download = AsyncMock()
    monkeypatch.setattr("aiogram.client.bot.Bot.send_message", mock_send_message)
    monkeypatch.setattr(
        "src.multichannel_gateway.infrastructure.chatwoot_client.cw_client.ChatwootClient.deliver_channel_to_chatwoot_message",
        mock_deliver_message,
    )
    monkeypatch.setattr(
        "telegram.tg_attachments.download_telegram_attachment",
        mock_download,
    )
    monkeypatch.setattr(
        "telegram.tg_attachments.notify_telegram_user",
        mock_notify,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as cl:
        response = await cl.post(
            f"/ingest/incoming/telegram/{tg_settings.bots_config[0].connector_id}/webhook",
            json=raw_data,
        )
        await asyncio.sleep(1)

    assert response.status_code == 204
    _assert_delivery_confirmation_sent(mock_send_message)
    mock_notify.assert_called_once_with(
        ANY,
        tg_settings.bots_config[0].connector_id,
        "1234567890",
        tg_settings.oversize_file_message,
    )
    mock_download.assert_not_called()
    assert mock_deliver_message.call_args.kwargs["content"] == "Big file incoming"
    assert mock_deliver_message.call_args.kwargs["attachments"] is None


@pytest.mark.order(7)
@pytest.mark.asyncio(loop_scope="session")
async def test_telegram_chatwoot_multi_attachments_include_animation(
    monkeypatch: pytest.MonkeyPatch,
    start_session_and_workers: tuple[asyncio.Task[Any], asyncio.Task[Any]],
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
            "message_id": 304,
            "caption": "Multiple files",
            "document": {
                "file_id": "doc_1",
                "file_unique_id": "doc_1_uid",
                "file_name": "a.pdf",
                "mime_type": "application/pdf",
                "file_size": 1024,
            },
            "animation": {
                "file_id": "gif_1",
                "file_unique_id": "gif_1_uid",
                "file_name": "anim.gif",
                "mime_type": "image/gif",
                "file_size": 2048,
                "width": 320,
                "height": 240,
                "duration": 3,
            },
        },
        "update_id": 353411709,
    }

    async def _make_tmp_file(
        _bot_manager: Any, _connector_id: str, file_id: str
    ) -> bytes:
        return file_id.encode()

    mock_send_message = AsyncMock()
    mock_deliver_message = AsyncMock()
    mock_notify = AsyncMock()
    mock_download = AsyncMock(side_effect=_make_tmp_file)
    monkeypatch.setattr("aiogram.client.bot.Bot.send_message", mock_send_message)
    monkeypatch.setattr(
        "src.multichannel_gateway.infrastructure.chatwoot_client.cw_client.ChatwootClient.deliver_channel_to_chatwoot_message",
        mock_deliver_message,
    )
    monkeypatch.setattr(
        "telegram.tg_attachments.download_telegram_attachment",
        mock_download,
    )
    monkeypatch.setattr(
        "telegram.tg_attachments.notify_telegram_user",
        mock_notify,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as cl:
        response = await cl.post(
            f"/ingest/incoming/telegram/{tg_settings.bots_config[0].connector_id}/webhook",
            json=raw_data,
        )
        await asyncio.sleep(1)

    assert response.status_code == 204
    _assert_delivery_confirmation_sent(mock_send_message)
    assert mock_download.await_count == 2
    mock_notify.assert_not_called()

    attachments = mock_deliver_message.call_args.kwargs["attachments"]
    attachment_names = {attachment["filename"] for attachment in attachments}
    attachment_types = {
        attachment["filename"]: attachment["file_type"] for attachment in attachments
    }

    assert attachment_names == {"a.pdf", "anim.gif"}
    assert attachment_types["a.pdf"] == "file"
    assert attachment_types["anim.gif"] == "image"
