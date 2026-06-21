from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.multichannel_gateway.app.services.channel_to_chatwoot_orchestrator import (
    ChannelToChatwootOrchestrator,
)
from src.multichannel_gateway.core import Envelope, SenderInfo


@pytest.mark.asyncio
async def test_orchestrator_preserves_delta_chat_raw_external_id_when_anonymizing() -> None:
    channel = MagicMock()
    channel.build_channel_message = AsyncMock(
        return_value=(
            "idem-key",
            Envelope(
                idem_key="idem-key",
                channel="delta_chat",
                from_="delta_chat",
                to="chatwoot",
                connector_id="delta-chat-1",
                cw_inbox_id="2",
                cw_account_id="2",
                message_id="msg-1",
                sender=SenderInfo(
                    external_id="delta_chat_actor_1",
                    raw_external_id="user@example.org",
                    name="Delta User",
                ),
                payload={"text": "hello"},
                ts=1.0,
            ),
        )
    )
    channel.publish_channel_message = AsyncMock()

    registry = MagicMock()
    registry.get_channel.return_value = channel

    alias_store = MagicMock()
    alias_store.get_or_create_alias = AsyncMock(return_value="uuid-alias")

    orchestrator = ChannelToChatwootOrchestrator(
        registry=registry,
        anonymize_users=True,
        alias_store=alias_store,
    )

    await orchestrator.process("delta_chat", {"message_id": "msg-1"})

    channel.publish_channel_message.assert_awaited_once()
    published_envelope = channel.publish_channel_message.await_args.args[1]
    assert published_envelope.sender.external_id == "uuid-alias"
    assert published_envelope.sender.raw_external_id == "user@example.org"
    alias_store.get_or_create_alias.assert_awaited_once_with(
        "delta_chat", "delta_chat_actor_1"
    )
