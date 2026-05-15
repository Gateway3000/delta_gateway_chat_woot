from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from channels.telegram_channel.plugin_settings import BotConfig
from channels.telegram_channel.tg_channel import TelegramChannel
from channels.telegram_channel.tg_message_processor import TelegramMessageProcessor
from channels.telegram_channel.tg_routing import TelegramRouting
from channels.telegram_channel.tg_transport import TelegramTransport
from channels.telegram_channel.tg_wh_manager import TelegramWebhookManager
from src import ChannelDeliveryResult, Envelope, SenderInfo


class TestTelegramChannel:
    def test_get_route_by_connector_id(
        self,
        telegram_channel: TelegramChannel,
        routing: TelegramRouting,
        bot_config: BotConfig,
    ) -> None:
        result = telegram_channel.get_route_by_connector_id(bot_config.connector_id)
        expected = routing.get_route_by_connector_id(bot_config.connector_id)

        assert result == expected
        assert result["connector_id"] == bot_config.connector_id

    @pytest.mark.asyncio
    async def test_send_to_user(
        self,
        telegram_channel: TelegramChannel,
        transport: TelegramTransport,
        bot_config: BotConfig,
    ) -> None:
        message = {
            "channel": "telegram",
            "connector_id": bot_config.connector_id,
            "sender": {"external_id": "12345"},
            "payload": {"text": "Hello"},
        }

        with patch.object(
            transport, "send_to_telegram_user", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = ChannelDeliveryResult(ok=True)
            result = await telegram_channel.send_to_user(message)

            mock_send.assert_awaited_once_with(message)
            assert result.ok is True

    @pytest.mark.asyncio
    async def test_publish_channel_message(
        self,
        telegram_channel: TelegramChannel,
        processor: TelegramMessageProcessor,
        bot_config: BotConfig,
    ) -> None:
        idempotency_key = "key-1"
        envelope = Envelope(
            idem_key=idempotency_key,
            channel="telegram",
            from_="telegram",
            to="chatwoot",
            connector_id=bot_config.connector_id,
            cw_account_id=bot_config.cw_account_id,
            cw_inbox_id=bot_config.cw_inbox_id,
            message_id="123",
            sender=SenderInfo(external_id=12345),
            payload={"text": "hello"},
            ts=1.0,
        )
        raw_data: dict[str, Any] = {"connector_id": bot_config.connector_id}

        with patch.object(
            processor, "publish_channel_message", new_callable=AsyncMock
        ) as mock_pub:
            await telegram_channel.publish_channel_message(
                idempotency_key, envelope, raw_data
            )
            mock_pub.assert_awaited_once_with(idempotency_key, envelope, raw_data)

    @pytest.mark.asyncio
    async def test_publish_chatwoot_message(
        self,
        telegram_channel: TelegramChannel,
        processor: TelegramMessageProcessor,
        bot_config: BotConfig,
    ) -> None:
        raw_data = {
            "inbox": {"id": int(bot_config.cw_inbox_id)},
            "conversation": {"meta": {"sender": {"identifier": "12345"}}},
            "content": "reply",
        }
        cw_account_id = bot_config.cw_account_id

        with patch.object(
            processor, "publish_chatwoot_message", new_callable=AsyncMock
        ) as mock_pub:
            await telegram_channel.publish_chatwoot_message(raw_data, cw_account_id)
            mock_pub.assert_awaited_once_with(
                raw_data, cw_account_id, telegram_channel.channel
            )

    @pytest.mark.asyncio
    async def test_on_shutdown(
        self,
        telegram_channel: TelegramChannel,
        bot_manager: MagicMock,
    ) -> None:
        await telegram_channel.on_shutdown()
        bot_manager.close_sessions.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_build_channel_message(
        self, telegram_channel: TelegramChannel, processor: TelegramMessageProcessor
    ) -> None:
        raw_data = {"test": "data"}
        expected: tuple[str, Envelope] = ("key", MagicMock(spec=Envelope))

        with patch.object(
            processor, "build_channel_message", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = expected
            result = await telegram_channel.build_channel_message(raw_data)
            mock_build.assert_awaited_once_with(raw_data)
            assert result == expected

    @pytest.mark.asyncio
    async def test_on_prefork(
        self,
        telegram_channel: TelegramChannel,
        wh_manager: TelegramWebhookManager,
    ) -> None:
        with patch.object(wh_manager, "set_wh", new_callable=AsyncMock) as mock_set_wh:
            await telegram_channel.on_prefork()
            mock_set_wh.assert_awaited_once()
