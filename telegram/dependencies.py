from aiogram import Dispatcher

from src import pgmq
from telegram.handlers.basic_handlers import router as telegram_handler
from telegram.plugin_settings import TelegramSettings
from telegram.tg_adapter import TelegramAdapter
from telegram.tg_bot_manager import TelegramBotManager
from telegram.tg_gateway import TelegramGateway
from telegram.tg_io_processor import TelegramIOProcessor
from telegram.tg_routing import TelegramRouting
from telegram.tg_transport import TelegramTransport
from telegram.tg_wh_manager import TelegramWebhookManager

dp = Dispatcher()
dp.include_router(telegram_handler)

tg_settings = TelegramSettings()
tg_bot_manager = TelegramBotManager(tg_settings.bots_config)
tg_routing = TelegramRouting(tg_settings.bots_config)
tg_webhooks = TelegramWebhookManager(
    tg_settings.wh_domain, tg_settings.secret_token, tg_bot_manager
)
tg_transport = TelegramTransport(tg_bot_manager, dp)
tg_adapter = TelegramAdapter(tg_routing)
tg_processor = TelegramIOProcessor(
    tg_bot_manager,
    tg_transport,
    tg_adapter,
    tg_settings,
    pgmq,
    tg_settings.incoming_queue_name,
    tg_settings.outgoing_queue_name,
)
telegram_gateway = TelegramGateway(
    tg_bot_manager,
    tg_routing,
    tg_transport,
    tg_processor,
    tg_adapter,
    tg_webhooks,
)
