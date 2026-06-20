from pathlib import Path

from channels.delta_chat_channel.dc_channel import DeltaChatChannel
from channels.delta_chat_channel.dc_client import DeltaChatClient
from channels.delta_chat_channel.dc_message_processor import DeltaChatMessageProcessor
from channels.delta_chat_channel.dc_routing import DeltaChatRouting
from channels.delta_chat_channel.dc_settings import DeltaChatSettings
from channels.delta_chat_channel.dc_transport import DeltaChatTransport
from src import pgmq
from src.multichannel_gateway.app.wiring import identity_store

delta_chat_settings = DeltaChatSettings()
delta_chat_accounts = [
    account.model_copy(
        update={
            "storage_dir": account.storage_dir
            or str(Path(delta_chat_settings.deltachat_accounts_dir) / account.connector_id)
        }
    )
    for account in delta_chat_settings.delta_chat_accounts
]
delta_chat_settings = delta_chat_settings.model_copy(
    update={"delta_chat_accounts": delta_chat_accounts}
)

delta_chat_routing = DeltaChatRouting(delta_chat_settings.delta_chat_accounts)
delta_chat_client = DeltaChatClient(delta_chat_settings, delta_chat_routing)
delta_chat_transport = DeltaChatTransport(
    delta_chat_settings,
    delta_chat_routing,
    delta_chat_client,
    identity_store,
)
delta_chat_processor = DeltaChatMessageProcessor(
    delta_chat_routing,
    delta_chat_transport,
    identity_store,
    pgmq,
    delta_chat_settings.incoming_queue_name,
    delta_chat_settings.outgoing_queue_name,
)
delta_chat_channel = DeltaChatChannel(
    delta_chat_routing,
    delta_chat_client,
    delta_chat_transport,
    delta_chat_processor,
)
