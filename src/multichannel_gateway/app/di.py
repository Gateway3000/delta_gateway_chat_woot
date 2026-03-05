from src.multichannel_gateway.app.config import Settings
from src.multichannel_gateway.app.workers.incoming import IncomingWorker
from src.multichannel_gateway.app.workers.outgoing import OutgoingWorker
from src.multichannel_gateway.infrastructure.chatwoot_client.cw_client import (
    ChatwootClient,
)
from src.multichannel_gateway.infrastructure.pg_conn_manager import ConnManager
from src.multichannel_gateway.infrastructure.pg_message_queue import PGMessageQueue
from src.multichannel_gateway.infrastructure.registry import GatewayRegistry
from src.multichannel_gateway.infrastructure.session_manager import HTTPSessionManager

settings: Settings = Settings()

conn_manager: ConnManager = ConnManager(settings.db_url)

pgmq: PGMessageQueue = PGMessageQueue(settings, conn_manager)

cw_session_manager: HTTPSessionManager = HTTPSessionManager()

cwc: ChatwootClient = ChatwootClient(
    settings.chatwoot_access_token, settings.chatwoot_base_url, cw_session_manager
)

registry: GatewayRegistry = GatewayRegistry()

incoming_worker: IncomingWorker = IncomingWorker(
    pgmq, cwc, settings.incoming_queue_name, registry
)
outgoing_worker: OutgoingWorker = OutgoingWorker(
    pgmq, settings.outgoing_queue_name, registry
)
