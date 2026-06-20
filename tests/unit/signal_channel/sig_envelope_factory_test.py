import pytest

from channels.signal_channel.plugin_settings import BotConfig
from channels.signal_channel.sig_envelope_factory import SignalEnvelopeFactory
from src.multichannel_gateway import WrongUpdateTypeError
from tests.unit.signal_channel.conftest import make_item

# A real 1:1 text message envelope (from the sample receive payload).
TEXT_ENVELOPE = {
    "source": "2647ff35-bb65-4459-90d8-c5c832c04d08",
    "sourceNumber": None,
    "sourceUuid": "2647ff35-bb65-4459-90d8-c5c832c04d08",
    "sourceName": "Anatoly Novikov",
    "sourceDevice": 1,
    "timestamp": 1781965264745,
    "dataMessage": {
        "timestamp": 1781965264745,
        "message": "Hi",
        "expiresInSeconds": 0,
        "isExpirationUpdate": False,
        "viewOnce": False,
    },
}

# Non-actionable envelope kinds that must be filtered out.
SYNC_ENVELOPE = {
    "source": "+4917624102926",
    "sourceName": "dima",
    "timestamp": 1781965255578,
    "syncMessage": {},
}
RECEIPT_ENVELOPE = {
    "source": "2647ff35-bb65-4459-90d8-c5c832c04d08",
    "sourceName": "Anatoly Novikov",
    "timestamp": 1781965270608,
    "receiptMessage": {"when": 1781965270608, "isDelivery": True, "isRead": False},
}
TYPING_ENVELOPE = {
    "source": "2647ff35-bb65-4459-90d8-c5c832c04d08",
    "sourceName": "Anatoly Novikov",
    "timestamp": 1781965276499,
    "typingMessage": {"action": "STARTED", "timestamp": 1781965276499},
}
GROUP_TEXT_ENVELOPE = {
    "source": "2647ff35-bb65-4459-90d8-c5c832c04d08",
    "sourceName": "Anatoly Novikov",
    "timestamp": 1781965264999,
    "dataMessage": {
        "timestamp": 1781965264999,
        "message": "Hi group",
        "groupInfo": {"groupId": "abc=="},
    },
}
EMPTY_TEXT_ENVELOPE = {
    "source": "2647ff35-bb65-4459-90d8-c5c832c04d08",
    "sourceName": "Anatoly Novikov",
    "timestamp": 1781965264998,
    "dataMessage": {"timestamp": 1781965264998, "message": "   "},
}


class TestSignalEnvelopeFactory:
    def test_parse_one_to_one_text_message(
        self, envelope_factory: SignalEnvelopeFactory, bot_config: BotConfig
    ) -> None:
        idem_key, envelope = envelope_factory.parse_channel_request(
            make_item(TEXT_ENVELOPE), bot_config.connector_id, "signal"
        )

        assert idem_key == envelope.idem_key
        assert envelope.channel == "signal"
        assert envelope.to == "chatwoot"
        assert envelope.connector_id == bot_config.connector_id
        assert envelope.cw_account_id == bot_config.cw_account_id
        assert envelope.cw_inbox_id == bot_config.cw_inbox_id
        assert envelope.message_id == "1781965264745"
        assert envelope.sender.external_id == "2647ff35-bb65-4459-90d8-c5c832c04d08"
        assert envelope.sender.name == "Anatoly Novikov"
        assert envelope.payload["text"] == "Hi"
        assert envelope.payload["attachments"] == []

    @pytest.mark.parametrize(
        "raw_envelope",
        [
            SYNC_ENVELOPE,
            RECEIPT_ENVELOPE,
            TYPING_ENVELOPE,
            GROUP_TEXT_ENVELOPE,
            EMPTY_TEXT_ENVELOPE,
        ],
    )
    def test_non_text_one_to_one_envelopes_are_rejected(
        self,
        envelope_factory: SignalEnvelopeFactory,
        bot_config: BotConfig,
        raw_envelope: dict,
    ) -> None:
        with pytest.raises(WrongUpdateTypeError):
            envelope_factory.parse_channel_request(
                make_item(raw_envelope), bot_config.connector_id, "signal"
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
