from src import pgmq
from telegram.plugin_settings import TelegramSettings
from telegram.tg_bot_manager import TelegramBotManager
from telegram.tg_channel import TelegramChannel
from telegram.tg_envelope_factory import TelegramEnvelopeFactory
from telegram.tg_message_processor import TelegramMessageProcessor
from telegram.tg_routing import TelegramRouting
from telegram.tg_transport import TelegramTransport
from telegram.tg_wh_manager import TelegramWebhookManager

tg_settings = TelegramSettings()
tg_bot_manager = TelegramBotManager(tg_settings.bots_config)
tg_routing = TelegramRouting(tg_settings.bots_config)
tg_webhooks = TelegramWebhookManager(
    tg_settings.wh_domain, tg_settings.secret_token, tg_bot_manager
)
tg_transport = TelegramTransport(tg_bot_manager)
tg_envelope_factory = TelegramEnvelopeFactory(tg_routing)
tg_processor = TelegramMessageProcessor(
    tg_bot_manager,
    tg_transport,
    tg_envelope_factory,
    tg_settings,
    pgmq,
    tg_settings.incoming_queue_name,
    tg_settings.outgoing_queue_name,
)
telegram_channel = TelegramChannel(
    tg_bot_manager,
    tg_routing,
    tg_transport,
    tg_processor,
    tg_webhooks,
)
