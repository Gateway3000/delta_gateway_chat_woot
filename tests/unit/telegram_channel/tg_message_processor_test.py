from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from channels.telegram_channel.plugin_settings import BotConfig
from channels.telegram_channel.tg_message_processor import TelegramMessageProcessor
from src import (
    ConnectorNotFoundError,
    Envelope,
    IdempotencyKeyAlreadyProcessedError,
    SenderInfo,
)


def _envelope(bot_config: BotConfig) -> Envelope:
    return Envelope(
        idem_key="key-1",
        channel="telegram",
        from_="telegram",
        to="chatwoot",
        connector_id=bot_config.connector_id,
        cw_account_id=bot_config.cw_account_id,
        cw_inbox_id=bot_config.cw_inbox_id,
        message_id="42",
        sender=SenderInfo(external_id=12345),
        payload={"text": "hello"},
        ts=1.0,
    )


class TestTelegramMessageProcessor:
    @pytest.mark.asyncio
    async def test_publish_channel_message_sends_and_marks_processed(
        self,
        mq: AsyncMock,
        processor: TelegramMessageProcessor,
        bot_config: BotConfig,
    ) -> None:
        mq.is_already_processed.return_value = False
        raw_data = {"connector_id": bot_config.connector_id}

        await processor.publish_channel_message(
            "key-1", _envelope(bot_config), raw_data
        )

        mq.is_already_processed.assert_awaited_once_with("key-1")
        mq.send.assert_awaited_once()
        mq.mark_as_processed.assert_awaited_once_with("key-1")

    @pytest.mark.asyncio
    async def test_publish_channel_message_raises_on_duplicate_idempotency(
        self,
        mq: AsyncMock,
        processor: TelegramMessageProcessor,
        bot_config: BotConfig,
    ) -> None:
        mq.is_already_processed.return_value = True
        raw_data = {"connector_id": bot_config.connector_id}

        with pytest.raises(IdempotencyKeyAlreadyProcessedError):
            await processor.publish_channel_message(
                "key-1", _envelope(bot_config), raw_data
            )

        mq.send.assert_not_awaited()
        mq.mark_as_processed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_publish_chatwoot_message_sends_to_outgoing_queue(
        self,
        mq: AsyncMock,
        processor: TelegramMessageProcessor,
        bot_config: BotConfig,
    ) -> None:
        mq.is_already_processed.return_value = False

        raw_data = {
            "inbox": {"id": int(bot_config.cw_inbox_id)},
            "conversation": {
                "meta": {"sender": {"identifier": "12345"}},
                "messages": [{"id": 321}],
            },
            "content": "reply body",
            "attachments": [],
        }

        await processor.publish_chatwoot_message(
            raw_data, bot_config.cw_account_id, "telegram"
        )

        mq.is_already_processed.assert_awaited_once()
        mq.send.assert_awaited_once()
        queue_name = mq.send.await_args.args[0]
        assert queue_name == "from_cw"
        mq.mark_as_processed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_publish_chatwoot_message_raises_on_duplicate_idempotency(
        self,
        mq: AsyncMock,
        processor: TelegramMessageProcessor,
        bot_config: BotConfig,
    ) -> None:
        mq.is_already_processed.return_value = True

        raw_data = {
            "inbox": {"id": int(bot_config.cw_inbox_id)},
            "conversation": {
                "meta": {"sender": {"identifier": "12345"}},
                "messages": [{"id": 321}],
            },
            "content": "reply body",
        }

        with pytest.raises(IdempotencyKeyAlreadyProcessedError):
            await processor.publish_chatwoot_message(
                raw_data, bot_config.cw_account_id, "telegram"
            )

        mq.send.assert_not_awaited()
        mq.mark_as_processed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_build_channel_message_returns_envelope(
        self,
        processor: TelegramMessageProcessor,
        bot_config: BotConfig,
    ) -> None:
        raw_data = {
            "connector_id": bot_config.connector_id,
            "channel": "telegram",
            "message": {
                "message_id": 42,
                "from": {"id": 12345, "first_name": "John"},
                "text": "Hello",
            },
        }

        idempotency_key, envelope = await processor.build_channel_message(raw_data)

        assert idempotency_key == envelope.idem_key
        assert envelope.channel == "telegram"
        assert envelope.connector_id == bot_config.connector_id
        assert envelope.cw_account_id == bot_config.cw_account_id

    @pytest.mark.asyncio
    async def test_publish_channel_message_raises_on_queue_failure(
        self,
        mq: AsyncMock,
        processor: TelegramMessageProcessor,
        bot_config: BotConfig,
    ) -> None:
        mq.is_already_processed.return_value = False
        mq.send.side_effect = Exception("test queue error")
        raw_data = {"connector_id": bot_config.connector_id}

        with pytest.raises(Exception, match="test queue error"):
            await processor.publish_channel_message(
                "key-1", _envelope(bot_config), raw_data
            )

    @pytest.mark.asyncio
    async def test_publish_channel_message_raises_on_unknown_connector(
        self,
        processor: TelegramMessageProcessor,
        bot_manager: MagicMock,
    ) -> None:
        bot_manager.get_bot_by_connector_id.return_value = None
        raw_data = {"connector_id": "nonexistent"}
        envelope = _envelope(
            BotConfig(
                connector_id="unused",
                bot_token="x",
                cw_account_id="0",
                cw_inbox_id="0",
            )
        )

        with pytest.raises(
            ConnectorNotFoundError, match="Unknown connector_id=nonexistent"
        ):
            await processor.publish_channel_message("key-1", envelope, raw_data)

    @pytest.mark.asyncio
    async def test_publish_channel_message_sends_delivery_confirmation(
        self,
        mq: AsyncMock,
        processor: TelegramMessageProcessor,
        bot_config: BotConfig,
        tg_bot: Mock,
    ) -> None:
        mq.is_already_processed.return_value = False
        processor._settings.enable_channel_delivery_confirmation = True  # type: ignore[attr-defined]
        raw_data = {
            "connector_id": bot_config.connector_id,
            "message": {"chat": {"id": 12345}},
        }

        await processor.publish_channel_message(
            "key-1", _envelope(bot_config), raw_data
        )

        tg_bot.send_message.assert_awaited_once_with(
            chat_id=12345, text="Your message was sent successfully!"
        )
        mq.send.assert_awaited_once()
        mq.mark_as_processed.assert_awaited_once()
