from unittest.mock import AsyncMock

import pytest

from channels.delta_chat_channel.dc_channel import DeltaChatChannel
from channels.delta_chat_channel.dc_message_processor import DeltaChatMessageProcessor
from channels.delta_chat_channel.dc_transport import DeltaChatTransport
from src import ChannelDeliveryResult, Envelope, SenderInfo


class TestDeltaChatChannel:
    def test_get_route_by_connector_id(self, channel: DeltaChatChannel, routing, account_config) -> None:
        result = channel.get_route_by_connector_id(account_config.connector_id)

        assert result == routing.get_route_by_connector_id(account_config.connector_id)

    @pytest.mark.asyncio
    async def test_send_to_user(self, channel: DeltaChatChannel, transport: DeltaChatTransport, account_config) -> None:
        message = {
            "channel": "delta_chat",
            "connector_id": account_config.connector_id,
            "sender": {"external_id": "chatwoot_actor_1"},
            "payload": {"text": "Hello"},
        }

        transport.send_to_delta_chat_user = AsyncMock(return_value=ChannelDeliveryResult(ok=True))  # type: ignore[method-assign]
        result = await channel.send_to_user(message)

        transport.send_to_delta_chat_user.assert_awaited_once_with(message)
        assert result.ok is True

    @pytest.mark.asyncio
    async def test_publish_channel_message(
        self, channel: DeltaChatChannel, processor: DeltaChatMessageProcessor, account_config
    ) -> None:
        idempotency_key = "key-1"
        envelope = Envelope(
            idem_key=idempotency_key,
            channel="delta_chat",
            from_="delta_chat",
            to="chatwoot",
            connector_id=account_config.connector_id,
            cw_account_id=account_config.cw_account_id,
            cw_inbox_id=account_config.cw_inbox_id,
            message_id="msg-1",
            sender=SenderInfo(external_id="delta_chat_actor_1"),
            payload={"text": "hello"},
            ts=1.0,
        )
        raw_data = {"sender_address": "bot1@example.org", "message_id": "msg-1", "chat_id": "chat-1"}

        processor.publish_channel_message = AsyncMock()  # type: ignore[method-assign]
        await channel.publish_channel_message(idempotency_key, envelope, raw_data)

        processor.publish_channel_message.assert_awaited_once_with(idempotency_key, envelope, raw_data)

    @pytest.mark.asyncio
    async def test_publish_chatwoot_message(
        self, channel: DeltaChatChannel, processor: DeltaChatMessageProcessor, account_config
    ) -> None:
        raw_data = {
            "inbox": {"id": int(account_config.cw_inbox_id)},
            "conversation": {"meta": {"sender": {"identifier": "chatwoot_actor_1"}}, "messages": [{"id": "cw-msg-1"}]},
            "content": "reply",
        }

        processor.publish_chatwoot_message = AsyncMock()  # type: ignore[method-assign]
        await channel.publish_chatwoot_message(raw_data, account_config.cw_account_id)

        processor.publish_chatwoot_message.assert_awaited_once_with(raw_data, account_config.cw_account_id)

    @pytest.mark.asyncio
    async def test_on_startup_and_shutdown(self, channel: DeltaChatChannel, client) -> None:
        client.start = AsyncMock()
        client.stop = AsyncMock()

        await channel.on_startup()
        await channel.on_shutdown()

        client.start.assert_awaited_once()
        client.stop.assert_awaited_once()

