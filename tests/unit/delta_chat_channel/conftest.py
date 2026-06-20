from unittest.mock import AsyncMock, MagicMock

import pytest

from channels.delta_chat_channel.dc_channel import DeltaChatChannel
from channels.delta_chat_channel.dc_client import DeltaChatClient
from channels.delta_chat_channel.dc_message_processor import DeltaChatMessageProcessor
from channels.delta_chat_channel.dc_models import DeltaChatAccountConfig
from channels.delta_chat_channel.dc_routing import DeltaChatRouting
from channels.delta_chat_channel.dc_settings import DeltaChatSettings
from channels.delta_chat_channel.dc_transport import DeltaChatTransport
from src import PGMessageQueue


@pytest.fixture
def account_config() -> DeltaChatAccountConfig:
    return DeltaChatAccountConfig(
        connector_id="delta-client-1",
        address="bot1@example.org",
        password="secret",
        display_name="Support Bot 1",
        avatar_path="/data/bot1/avatar.jpg",
        bridge_url="https://bridge.example.org",
        cw_account_id="1",
        cw_inbox_id="5",
    )


@pytest.fixture
def settings(account_config: DeltaChatAccountConfig) -> DeltaChatSettings:
    return DeltaChatSettings(
        delta_chat_accounts=[account_config],
        deltachat_accounts_dir="/tmp/deltachat",
        enable_native_deltachat_channel=False,
    )


@pytest.fixture
def routing(settings: DeltaChatSettings) -> DeltaChatRouting:
    return DeltaChatRouting(settings.delta_chat_accounts)


@pytest.fixture
def client(settings: DeltaChatSettings, routing: DeltaChatRouting) -> MagicMock:
    return MagicMock(spec=DeltaChatClient)


@pytest.fixture
def identity_store() -> MagicMock:
    store = MagicMock()
    store.get_or_create_actor_id = AsyncMock(return_value="delta_chat_actor_1")
    store.resolve_external_id = AsyncMock(return_value="bot1@example.org")
    return store


@pytest.fixture
def transport(
    settings: DeltaChatSettings,
    routing: DeltaChatRouting,
    client: MagicMock,
    identity_store: MagicMock,
) -> DeltaChatTransport:
    return DeltaChatTransport(settings, routing, client, identity_store)


@pytest.fixture
def mq() -> AsyncMock:
    return AsyncMock(spec=PGMessageQueue)


@pytest.fixture
def processor(
    routing: DeltaChatRouting,
    transport: DeltaChatTransport,
    identity_store: MagicMock,
    mq: AsyncMock,
) -> DeltaChatMessageProcessor:
    return DeltaChatMessageProcessor(routing, transport, identity_store, mq, "to_cw", "from_cw")


@pytest.fixture
def channel(
    routing: DeltaChatRouting,
    client: MagicMock,
    transport: DeltaChatTransport,
    processor: DeltaChatMessageProcessor,
) -> DeltaChatChannel:
    return DeltaChatChannel(routing, client, transport, processor)

