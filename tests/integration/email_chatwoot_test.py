import asyncio
from typing import Any
from unittest.mock import AsyncMock

import asyncpg
import pytest

from email_channel.email_wiring import email_settings
from src.multichannel_gateway.infrastructure.endpoints import handle_channel_payload


@pytest.mark.order(8)
@pytest.mark.asyncio(loop_scope="session")
async def test_email_chatwoot(
    monkeypatch: pytest.MonkeyPatch,
    start_session_and_workers: tuple[asyncio.Task[Any], asyncio.Task[Any]],
    get_db_pool: asyncpg.Pool,
) -> None:
    connector_id = email_settings.mailboxes_config[0].connector_id
    raw_data = {
        "channel": "email",
        "connector_id": connector_id,
        "uid": 12345,
        "uidvalidity": 777,
        "message_id": "<test123@example.com>",
        "subject": "Test Subject",
        "text": "Test email body",
        "sender": {
            "email": email_settings.mailboxes_config[0].imap_username,
            "name": "Test User",
        },
    }

    mock_deliver_message = AsyncMock()
    monkeypatch.setattr(
        "src.multichannel_gateway.infrastructure.chatwoot_client.cw_client.ChatwootClient.deliver_channel_to_chatwoot_message",
        mock_deliver_message,
    )

    await handle_channel_payload("email", connector_id, raw_data)
    await asyncio.sleep(1)

    async with get_db_pool.acquire() as conn:
        q_to_cw_res = await conn.fetch("SELECT COUNT(*) FROM pgmq.q_to_cw")
        processed_keys_res = await conn.fetchrow(
            "SELECT * FROM pgmq.processed_keys ORDER BY key DESC LIMIT 1"
        )

    assert q_to_cw_res[0]["count"] == 0
    assert processed_keys_res["key"] is not None
    assert "12345" in processed_keys_res["key"]
    mock_deliver_message.assert_called()
    test_call_found = any(
        "Test Subject" in str(call.kwargs.get("content", ""))
        for call in mock_deliver_message.call_args_list
    )
    assert test_call_found

    # ========== CHECK THE SECOND CALL WITH THE SAME ARGUMENTS =========
    # Should return 200 (idempotency key already processed)
    call_count_before = mock_deliver_message.call_count
    result = await handle_channel_payload("email", connector_id, raw_data)
    assert result is not None
    assert result.status_code == 200
    # Verify Chatwoot was NOT called again
    assert mock_deliver_message.call_count == call_count_before


@pytest.mark.order(9)
@pytest.mark.asyncio(loop_scope="session")
async def test_email_chatwoot_with_attachments(
    monkeypatch: pytest.MonkeyPatch,
    start_session_and_workers: tuple[asyncio.Task[Any], asyncio.Task[Any]],
) -> None:
    connector_id = email_settings.mailboxes_config[0].connector_id
    raw_data = {
        "channel": "email",
        "connector_id": connector_id,
        "uid": 12346,
        "uidvalidity": 777,
        "message_id": "<test456@example.com>",
        "subject": "With Attachment",
        "text": "See attached",
        "sender": {
            "email": email_settings.mailboxes_config[0].imap_username,
            "name": "Test User",
        },
        "attachments": [
            {
                "filename": "test.txt",
                "mime_type": "text/plain",
                "size": 100,
                "data": "base64encoded==",
            }
        ],
    }

    mock_deliver_message = AsyncMock()
    monkeypatch.setattr(
        "src.multichannel_gateway.infrastructure.chatwoot_client.cw_client.ChatwootClient.deliver_channel_to_chatwoot_message",
        mock_deliver_message,
    )

    await handle_channel_payload("email", connector_id, raw_data)
    await asyncio.sleep(1)

    mock_deliver_message.assert_called_once()
    call_kwargs = mock_deliver_message.call_args.kwargs
    assert "attachments" in call_kwargs
    assert len(call_kwargs["attachments"]) == 1
    assert call_kwargs["attachments"][0]["filename"] == "test.txt"
