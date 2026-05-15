from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from channels.telegram_channel.plugin_settings import TelegramSettings, BotConfig
from channels.telegram_channel.tg_bot_manager import TelegramBotManager
from channels.telegram_channel.tg_channel import TelegramChannel
from channels.telegram_channel.tg_envelope_factory import TelegramEnvelopeFactory
from channels.telegram_channel.tg_message_processor import TelegramMessageProcessor
from channels.telegram_channel.tg_routing import TelegramRouting
from channels.telegram_channel.tg_transport import TelegramTransport
from channels.telegram_channel.tg_wh_manager import TelegramWebhookManager
from src import PGMessageQueue


@pytest.fixture
def bot_config() -> BotConfig:
    return BotConfig(
        connector_id="tg_test",
        bot_token="123456:TESTTOKEN",
        cw_account_id="3",
        cw_inbox_id="18",
    )


@pytest.fixture
def settings(bot_config: BotConfig) -> TelegramSettings:
    return TelegramSettings(
        bots_config=[bot_config],
        enable_channel_delivery_confirmation=False,
    )


@pytest.fixture
def routing(settings: TelegramSettings) -> TelegramRouting:
    return TelegramRouting(settings.bots_config)


@pytest.fixture
def envelope_factory(routing: TelegramRouting) -> TelegramEnvelopeFactory:
    return TelegramEnvelopeFactory(routing)


@pytest.fixture
def tg_bot() -> Mock:
    bot = Mock()
    bot.get_file = AsyncMock()
    bot.download_file = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def default_settings() -> TelegramSettings:
    return TelegramSettings(
        channel_upload_max_mb=20,
        chatwoot_upload_max_mb=40,
        oversize_file_message="too large",
        enable_channel_delivery_confirmation=False,
    )


@pytest.fixture
def bot_manager(tg_bot: Mock) -> MagicMock:
    manager = MagicMock(spec=TelegramBotManager)
    manager.close_sessions = AsyncMock()
    manager.get_bot_by_connector_id.return_value = tg_bot
    return manager


@pytest.fixture
def transport(bot_manager: MagicMock) -> TelegramTransport:
    return TelegramTransport(bot_manager)


@pytest.fixture
def mq() -> AsyncMock:
    return AsyncMock(spec=PGMessageQueue)


@pytest.fixture
def processor(
    bot_manager: MagicMock,
    transport: TelegramTransport,
    envelope_factory: TelegramEnvelopeFactory,
    settings: TelegramSettings,
    mq: AsyncMock,
) -> TelegramMessageProcessor:
    return TelegramMessageProcessor(
        bot_manager,
        transport,
        envelope_factory,
        settings,
        mq,
        "to_cw",
        "from_cw",
    )


@pytest.fixture
def wh_manager(
    settings: TelegramSettings,
    bot_manager: MagicMock,
) -> TelegramWebhookManager:
    return TelegramWebhookManager(
        "https://example.com",
        "test-secret",
        bot_manager,
    )


@pytest.fixture
def telegram_channel(
    bot_manager: MagicMock,
    routing: TelegramRouting,
    transport: TelegramTransport,
    processor: TelegramMessageProcessor,
    wh_manager: TelegramWebhookManager,
) -> TelegramChannel:
    return TelegramChannel(
        bot_manager,
        routing,
        transport,
        processor,
        wh_manager,
    )
