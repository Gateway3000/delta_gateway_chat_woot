from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from channels.delta_chat_channel.dc_message_processor import DeltaChatMessageProcessor
from channels.delta_chat_channel.dc_models import DeltaChatAccountConfig
from channels.delta_chat_channel.dc_routing import DeltaChatRouting
from channels.delta_chat_channel.dc_settings import DeltaChatSettings
from channels.delta_chat_channel.dc_transport import DeltaChatTransport


@pytest.mark.asyncio
async def test_build_channel_message_produces_expected_envelope(
    routing, identity_store
) -> None:
    settings = DeltaChatSettings(
        delta_chat_accounts=[
            DeltaChatAccountConfig(
                connector_id="delta-client-1",
                address="bot1@example.org",
                password="secret",
                cw_account_id="1",
                cw_inbox_id="5",
            )
        ],
        deltachat_accounts_dir="/tmp/deltachat",
        enable_native_deltachat_channel=True,
    )
    client = MagicMock()
    transport = DeltaChatTransport(settings, routing, client, identity_store)
    mq = AsyncMock()
    processor = DeltaChatMessageProcessor(
        routing,
        transport,
        identity_store,
        mq,
        "to_cw",
        "from_cw",
    )

    raw_data = {
        "account_id": 7,
        "connector_id": "delta-client-1",
        "message_id": "msg-1",
        "chat_id": 42,
        "sender_id": "sender-1",
        "sender_address": "user@example.org",
        "sender_name": "Delta User",
        "text": "Hello from Delta Chat",
        "attachments": [],
        "is_group": False,
        "is_info": False,
    }

    idempotency_key, envelope = await processor.build_channel_message(raw_data)

    assert idempotency_key.startswith("delta_chat->chatwoot:delta-client-1:")
    assert envelope.channel == "delta_chat"
    assert envelope.from_ == "delta_chat"
    assert envelope.to == "chatwoot"
    assert envelope.connector_id == "delta-client-1"
    assert envelope.cw_account_id == "1"
    assert envelope.cw_inbox_id == "5"
    assert envelope.message_id == "msg-1"
    assert envelope.sender.external_id == "delta_chat_actor_1"
    assert envelope.sender.raw_external_id == "user@example.org"
    assert envelope.payload["text"] == "Hello from Delta Chat"
    assert envelope.payload["chat_id"] == "42"


@pytest.mark.asyncio
async def test_publish_channel_message_enqueues_to_incoming_queue(
    routing, identity_store
) -> None:
    settings = DeltaChatSettings(
        delta_chat_accounts=[
            DeltaChatAccountConfig(
                connector_id="delta-client-1",
                address="bot1@example.org",
                password="secret",
                cw_account_id="1",
                cw_inbox_id="5",
            )
        ],
        deltachat_accounts_dir="/tmp/deltachat",
        enable_native_deltachat_channel=True,
    )
    client = MagicMock()
    transport = DeltaChatTransport(settings, routing, client, identity_store)
    mq = AsyncMock()
    mq.is_already_processed = AsyncMock(return_value=False)
    mq.send = AsyncMock()
    mq.mark_as_processed = AsyncMock()
    processor = DeltaChatMessageProcessor(
        routing,
        transport,
        identity_store,
        mq,
        "to_cw",
        "from_cw",
    )

    raw_data = {
        "account_id": 7,
        "connector_id": "delta-client-1",
        "message_id": "msg-1",
        "chat_id": 42,
        "sender_id": "sender-1",
        "sender_address": "user@example.org",
        "sender_name": "Delta User",
        "text": "Hello from Delta Chat",
        "attachments": [],
        "is_group": False,
        "is_info": False,
    }

    idempotency_key, envelope = await processor.build_channel_message(raw_data)
    await processor.publish_channel_message(idempotency_key, envelope, raw_data)

    mq.send.assert_awaited_once()
    queue_name, payload = mq.send.await_args.args
    assert queue_name == "to_cw"
    assert payload["channel"] == "delta_chat"
    assert payload["payload"]["text"] == "Hello from Delta Chat"
    mq.mark_as_processed.assert_awaited_once_with(idempotency_key)
