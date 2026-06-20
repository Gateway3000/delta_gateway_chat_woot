import pytest

from channels.signal_channel.plugin_settings import BotConfig
from channels.signal_channel.sig_envelope_factory import SignalEnvelopeFactory
from src.multichannel_gateway import WrongUpdateTypeError
from tests.unit.signal_channel.conftest import make_message


class TestSignalEnvelopeFactory:
    def test_parse_one_to_one_text_message(
        self, envelope_factory: SignalEnvelopeFactory, bot_config: BotConfig
    ) -> None:
        idem_key, envelope = envelope_factory.parse_channel_request(
            make_message(), bot_config.connector_id, "signal"
        )

        assert idem_key == envelope.idem_key
        assert envelope.channel == "signal"
        assert envelope.to == "chatwoot"
        assert envelope.connector_id == bot_config.connector_id
        assert envelope.cw_account_id == bot_config.cw_account_id
        assert envelope.cw_inbox_id == bot_config.cw_inbox_id
        assert envelope.message_id == "1781965264745"
        assert envelope.sender.external_id == "2647ff35-bb65-4459-90d8-c5c832c04d08"
        assert envelope.sender.name == "Ellie"
        assert envelope.payload["text"] == "Hi"
        assert envelope.payload["attachments"] == []

    @pytest.mark.parametrize(
        "mutation",
        [
            {"type": "send_result"},  # not a message event
            {"type": "queue_empty"},
            {"message": ""},  # empty body
            {"message": "   "},  # whitespace-only body
            {"source_uuid": None},  # missing sender
            {"timestamp": None},  # missing timestamp
        ],
    )
    def test_non_text_one_to_one_events_are_rejected(
        self,
        envelope_factory: SignalEnvelopeFactory,
        bot_config: BotConfig,
        mutation: dict,
    ) -> None:
        event = make_message()
        event.update(mutation)
        with pytest.raises(WrongUpdateTypeError):
            envelope_factory.parse_channel_request(
                event, bot_config.connector_id, "signal"
            )

    def test_parse_chatwoot_request_uses_identifier_as_recipient(
        self, envelope_factory: SignalEnvelopeFactory, bot_config: BotConfig
    ) -> None:
        raw_data = {
            "inbox": {"id": int(bot_config.cw_inbox_id)},
            "content": "Reply from agent",
            "conversation": {
                "meta": {
                    "sender": {"identifier": "2647ff35-bb65-4459-90d8-c5c832c04d08"}
                },
                "messages": [{"id": 555}],
            },
        }

        idem_key, envelope = envelope_factory.parse_chatwoot_request(
            raw_data, bot_config.cw_account_id, "signal"
        )

        assert idem_key == envelope.idem_key
        assert envelope.from_ == "chatwoot"
        assert envelope.to == "signal"
        assert envelope.sender.external_id == "2647ff35-bb65-4459-90d8-c5c832c04d08"
        assert envelope.payload["text"] == "Reply from agent"
