from aiogram import Dispatcher

from app.config import Settings
from app.workers.incoming import IncomingWorker
from app.workers.outgoing import OutgoingWorker
from infrastructure.pg_message_queue import PGMessageQueue
from infrastructure.registry import GatewayRegistry
from infrastructure.telegram.tg_adapter import TelegramAdapter
from infrastructure.telegram.tg_bot_manager import TelegramBotManager
from infrastructure.telegram.tg_gateway import TelegramGateway
from infrastructure.telegram.tg_io_processor import TelegramIOProcessor
from infrastructure.telegram.tg_routing import TelegramRouting
from infrastructure.telegram.tg_transport import TelegramTransport
from infrastructure.telegram.tg_wh_manager import TelegramWebhookManager

settings = Settings()
dp = Dispatcher()
tg_bot_manager = TelegramBotManager(settings.bots_config)
tg_routing = TelegramRouting(settings.bots_config)
tg_webhooks = TelegramWebhookManager(
    settings.wh_domain, settings.secret_token, tg_bot_manager
)
tg_transport = TelegramTransport(tg_bot_manager, dp)
tg_adapter = TelegramAdapter()
pgmq = PGMessageQueue(settings.db_url)
tg_processor = TelegramIOProcessor(
    tg_bot_manager,
    tg_routing,
    tg_transport,
    tg_adapter,
    pgmq,
    settings.incoming_queue_name,
    settings.outgoing_queue_name,
)
tg_gateway = TelegramGateway(
    tg_bot_manager, tg_routing, tg_webhooks, tg_transport, tg_adapter, tg_processor
)

gateways = GatewayRegistry()
gateways.register_gateway(tg_gateway)

incoming_worker = IncomingWorker(pgmq, settings.incoming_queue_name)
outgoing_worker = OutgoingWorker(pgmq, settings.outgoing_queue_name)
