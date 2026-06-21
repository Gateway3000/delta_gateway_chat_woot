import pytest

from channels.simplex_channel.plugin_settings import BotConfig
from channels.simplex_channel.sx_envelope_factory import SimplexEnvelopeFactory
from src.multichannel_gateway import WrongUpdateTypeError
from tests.unit.simplex_channel.conftest import make_message


class TestSimplexEnvelopeFactory:
    def test_parse_one_to_one_text_message(
        self, envelope_factory: SimplexEnvelopeFactory, bot_config: BotConfig
    ) -> None:
        idem_key, envelope = envelope_factory.parse_channel_request(
            make_message(), bot_config.connector_id, "simplex"
        )

        assert idem_key == envelope.idem_key
        assert envelope.channel == "simplex"
        assert envelope.to == "chatwoot"
        assert envelope.connector_id == bot_config.connector_id
        assert envelope.cw_account_id == bot_config.cw_account_id
        assert envelope.cw_inbox_id == bot_config.cw_inbox_id
        assert envelope.message_id == "1001"
        assert envelope.sender.external_id == "42"
        assert envelope.sender.name == "Alice"
        assert envelope.payload["text"] == "Hi"
        assert envelope.payload["attachments"] == []

    @pytest.mark.parametrize(
        "mutation",
        [
            {"type": "newChatItems"},  # not a normalized message event
            {"text": ""},  # empty body
            {"text": "   "},  # whitespace-only body
            {"source_id": None},  # missing sender
            {"item_id": None},  # missing item id
        ],
    )
    def test_invalid_events_are_rejected(
        self,
        envelope_factory: SimplexEnvelopeFactory,
        bot_config: BotConfig,
        mutation: dict,
    ) -> None:
        event = make_message()
        event.update(mutation)
        with pytest.raises(WrongUpdateTypeError):
            envelope_factory.parse_channel_request(
                event, bot_config.connector_id, "simplex"
            )

    def test_parse_chatwoot_request_uses_identifier_as_recipient(
        self, envelope_factory: SimplexEnvelopeFactory, bot_config: BotConfig
    ) -> None:
        raw_data = {
            "inbox": {"id": int(bot_config.cw_inbox_id)},
            "content": "Reply from agent",
            "conversation": {
                "meta": {"sender": {"identifier": "42"}},
                "messages": [{"id": 555}],
            },
        }

        idem_key, envelope = envelope_factory.parse_chatwoot_request(
            raw_data, bot_config.cw_account_id, "simplex"
        )

        assert idem_key == envelope.idem_key
        assert envelope.from_ == "chatwoot"
        assert envelope.to == "simplex"
        assert envelope.sender.external_id == "42"
        assert envelope.payload["text"] == "Reply from agent"
