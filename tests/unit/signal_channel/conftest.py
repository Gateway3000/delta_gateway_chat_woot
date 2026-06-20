import pytest

from channels.signal_channel.plugin_settings import BotConfig, SignalSettings
from channels.signal_channel.sig_envelope_factory import SignalEnvelopeFactory
from channels.signal_channel.sig_routing import SignalRouting


@pytest.fixture
def bot_config() -> BotConfig:
    return BotConfig(
        connector_id="sig1",
        number="+4917624102926",
        api_url="http://signal:8080",
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


def make_item(envelope: dict, *, connector_id: str = "sig1") -> dict:
    """Wrap a raw signal envelope the way the receiver hands it to the factory."""
    return {
        "envelope": envelope,
        "account": "+4917624102926",
        "channel": "signal",
        "connector_id": connector_id,
    }
