from aiogram import Dispatcher

from src.multichannel_gateway.app.di import settings, pgmq
from telegram.handlers.basic_handlers import router as telegram_handler
from telegram.tg_adapter import TelegramAdapter
from telegram.tg_bot_manager import TelegramBotManager
from telegram.tg_gateway import TelegramGateway
from telegram.tg_io_processor import TelegramIOProcessor
from telegram.tg_routing import TelegramRouting
from telegram.tg_transport import TelegramTransport
from telegram.tg_wh_manager import TelegramWebhookManager

dp = Dispatcher()
dp.include_router(telegram_handler)

tg_bot_manager = TelegramBotManager(settings.bots_config)
tg_routing = TelegramRouting(settings.bots_config)
tg_webhooks = TelegramWebhookManager(
    settings.wh_domain, settings.secret_token, tg_bot_manager
)
tg_transport = TelegramTransport(tg_bot_manager, dp)
tg_adapter = TelegramAdapter(tg_routing)
tg_processor = TelegramIOProcessor(
    tg_bot_manager,
    tg_transport,
    tg_adapter,
    pgmq,
    settings.incoming_queue_name,
    settings.outgoing_queue_name,
)
telegram_gateway = TelegramGateway(
    tg_bot_manager, tg_routing, tg_transport, tg_processor, tg_adapter, tg_webhooks
)
