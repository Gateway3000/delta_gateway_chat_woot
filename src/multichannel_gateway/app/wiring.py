from src.multichannel_gateway.app import Settings, TelemetrySettings
from src.multichannel_gateway.app.workers import (
    ChannelToChatwootWorker,
    ChatwootToChannelWorker,
)
from src.multichannel_gateway.infrastructure import (
    ChatwootClient,
    ConnManager,
    GatewayRegistry,
    HTTPSessionManager,
    PGMessageQueue,
)

settings: Settings = Settings()
telemetry_settings: TelemetrySettings = TelemetrySettings()

conn_manager: ConnManager = ConnManager(settings.db_url)

pgmq: PGMessageQueue = PGMessageQueue(settings, conn_manager)

cw_session_manager: HTTPSessionManager = HTTPSessionManager()

cwc: ChatwootClient = ChatwootClient(
    settings.chatwoot_access_token, settings.chatwoot_base_url, cw_session_manager
)

registry: GatewayRegistry = GatewayRegistry()

incoming_worker: ChannelToChatwootWorker = ChannelToChatwootWorker(
    settings, pgmq, cwc, settings.incoming_queue_name
)
outgoing_worker: ChatwootToChannelWorker = ChatwootToChannelWorker(
    pgmq, settings.outgoing_queue_name, registry
)
