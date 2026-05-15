import pytest

from channels.telegram_channel.plugin_settings import BotConfig
from channels.telegram_channel.tg_envelope_factory import TelegramEnvelopeFactory
from channels.telegram_channel.tg_routing import TelegramRouting
from src.multichannel_gateway import WrongUpdateTypeError
from src.multichannel_gateway.core.interfaces.envelope_factory import IEnvelopeFactory


class TestTelegramEnvelopeFactory:
    def test_parse_channel_request_builds_envelope(
        self,
        routing: TelegramRouting,
        bot_config: BotConfig,
        envelope_factory: TelegramEnvelopeFactory,
    ) -> None:
        raw_data = {
            "connector_id": bot_config.connector_id,
            "message": {
                "message_id": 42,
                "from": {
                    "id": 12345,
                    "first_name": "John",
                    "last_name": "Doe",
                    "username": "johndoe",
                },
                "text": "Hello from Telegram",
            },
        }

        idem_key, envelope = envelope_factory.parse_channel_request(
            raw_data,
            connector_id=bot_config.connector_id,
            channel="telegram",
        )

        assert idem_key == envelope.idem_key
        assert envelope.channel == "telegram"
        assert envelope.to == "chatwoot"
        assert envelope.connector_id == bot_config.connector_id
        assert envelope.cw_account_id == bot_config.cw_account_id
        assert envelope.cw_inbox_id == bot_config.cw_inbox_id
        assert envelope.message_id == "42"
        assert envelope.sender.external_id == 12345
        assert envelope.sender.nickname == "johndoe"
        assert envelope.payload["text"] == "Hello from Telegram"

    def test_parse_channel_request_missing_from_info_raises(
        self,
        routing: TelegramRouting,
        bot_config: BotConfig,
        envelope_factory: TelegramEnvelopeFactory,
    ) -> None:
        raw_data = {
            "connector_id": bot_config.connector_id,
            "message": {"message_id": 1, "text": "Hello"},
        }

        with pytest.raises(WrongUpdateTypeError):
            envelope_factory.parse_channel_request(
                raw_data,
                connector_id=bot_config.connector_id,
                channel="telegram",
            )

    def test_parse_channel_request_uses_caption_when_text_missing(
        self,
        routing: TelegramRouting,
        bot_config: BotConfig,
        envelope_factory: TelegramEnvelopeFactory,
    ) -> None:
        raw_data = {
            "connector_id": bot_config.connector_id,
            "message": {
                "message_id": 10,
                "from": {"id": 12345, "first_name": "John"},
                "caption": "Photo caption",
            },
        }

        _, envelope = envelope_factory.parse_channel_request(
            raw_data,
            connector_id=bot_config.connector_id,
            channel="telegram",
        )

        assert envelope.payload["text"] == "Photo caption"

    def test_parse_channel_request_empty_text_and_caption(
        self,
        routing: TelegramRouting,
        bot_config: BotConfig,
        envelope_factory: TelegramEnvelopeFactory,
    ) -> None:
        raw_data = {
            "connector_id": bot_config.connector_id,
            "message": {
                "message_id": 11,
                "from": {"id": 12345, "first_name": "John"},
            },
        }

        _, envelope = envelope_factory.parse_channel_request(
            raw_data,
            connector_id=bot_config.connector_id,
            channel="telegram",
        )

        assert envelope.payload["text"] == ""

    def test_parse_channel_request_uses_bot_token_suffix_in_idempotency_key(
        self,
        routing: TelegramRouting,
        bot_config: BotConfig,
        envelope_factory: TelegramEnvelopeFactory,
    ) -> None:
        raw_data = {
            "connector_id": bot_config.connector_id,
            "message": {
                "message_id": 7,
                "from": {"id": 999, "first_name": "Alice"},
                "text": "Hi",
            },
        }

        idem_key, _ = envelope_factory.parse_channel_request(
            raw_data,
            connector_id=bot_config.connector_id,
            channel="telegram",
        )

        expected_key = IEnvelopeFactory.build_idempotency_key(
            direction="telegram->chatwoot",
            connector_id=bot_config.connector_id,
            external_id="999",
            message_id="7",
            bot_token_suffix=bot_config.bot_token[-5:],
        )
        assert idem_key == expected_key

    def test_parse_chatwoot_request_builds_envelope(
        self,
        routing: TelegramRouting,
        bot_config: BotConfig,
        envelope_factory: TelegramEnvelopeFactory,
    ) -> None:
        raw_data = {
            "inbox": {"id": int(bot_config.cw_inbox_id)},
            "conversation": {
                "meta": {"sender": {"identifier": "12345"}},
                "messages": [{"id": 999, "content": "Reply message"}],
            },
            "content": "Reply message",
        }

        idem_key, envelope = envelope_factory.parse_chatwoot_request(
            raw_data,
            cw_account_id=bot_config.cw_account_id,
            channel="telegram",
        )

        assert idem_key == envelope.idem_key
        assert envelope.channel == "telegram"
        assert envelope.from_ == "chatwoot"
        assert envelope.to == "telegram"
        assert envelope.connector_id == bot_config.connector_id
        assert envelope.cw_inbox_id == str(bot_config.cw_inbox_id)
        assert envelope.cw_account_id == bot_config.cw_account_id
        assert envelope.message_id == "999"
        assert envelope.sender.external_id == "12345"
        assert envelope.payload["text"] == "Reply message"

    def test_parse_chatwoot_request_idempotency_key_format(
        self,
        routing: TelegramRouting,
        bot_config: BotConfig,
        envelope_factory: TelegramEnvelopeFactory,
    ) -> None:
        raw_data = {
            "inbox": {"id": int(bot_config.cw_inbox_id)},
            "conversation": {
                "meta": {"sender": {"identifier": "12345"}},
                "messages": [{"id": 999, "content": "Reply"}],
            },
        }

        idem_key, _ = envelope_factory.parse_chatwoot_request(
            raw_data,
            cw_account_id=bot_config.cw_account_id,
            channel="telegram",
        )

        expected_key = IEnvelopeFactory.build_idempotency_key(
            direction="chatwoot->telegram",
            connector_id=bot_config.connector_id,
            external_id="12345",
            message_id="999",
            bot_token_suffix=bot_config.bot_token[-5:],
        )
        assert idem_key == expected_key

    def test_parse_chatwoot_request_with_attachments(
        self,
        routing: TelegramRouting,
        bot_config: BotConfig,
        envelope_factory: TelegramEnvelopeFactory,
    ) -> None:
        raw_data = {
            "inbox": {"id": int(bot_config.cw_inbox_id)},
            "conversation": {
                "meta": {"sender": {"identifier": "12345"}},
                "messages": [{"id": 999, "content": "Reply"}],
            },
            "attachments": [
                {
                    "file_type": "image",
                    "file_name": "test.png",
                    "data_url": "data:image/png;base64,abc",
                    "content_type": "image/png",
                    "file_size": 1024,
                }
            ],
        }

        _, envelope = envelope_factory.parse_chatwoot_request(
            raw_data,
            cw_account_id=bot_config.cw_account_id,
            channel="telegram",
        )

        assert len(envelope.payload["attachments"]) == 1
        assert envelope.payload["attachments"][0]["filename"] == "test.png"
