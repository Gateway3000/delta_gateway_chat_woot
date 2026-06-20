import pytest

from channels.signal_channel.plugin_settings import BotConfig, SignalSettings
from channels.signal_channel.sig_envelope_factory import SignalEnvelopeFactory
from channels.signal_channel.sig_routing import SignalRouting


@pytest.fixture
def bot_config() -> BotConfig:
    return BotConfig(
        connector_id="sig1",
        number="+0000000000",
        host="signal-bridge",
        port=8080,
        cw_account_id="1",
        cw_inbox_id="11",
    )


@pytest.fixture
def settings(bot_config: BotConfig) -> SignalSettings:
    return SignalSettings(bots_config=[bot_config])


@pytest.fixture
def routing(bot_config: BotConfig) -> SignalRouting:
    return SignalRouting([bot_config])


@pytest.fixture
def envelope_factory(routing: SignalRouting) -> SignalEnvelopeFactory:
    return SignalEnvelopeFactory(routing)


def make_message(
    *,
    source_uuid: str = "2647ff35-bb65-4459-90d8-c5c832c04d08",
    source_name: str | None = "Ellie",
    message: str = "Hi",
    timestamp: int = 1781965264745,
    connector_id: str = "sig1",
) -> dict:
    """Build a signal-bridge `message` event as the receiver hands it to the factory."""
    return {
        "type": "message",
        "source_uuid": source_uuid,
        "source_name": source_name,
        "timestamp": timestamp,
        "message": message,
        "channel": "signal",
        "connector_id": connector_id,
    }
