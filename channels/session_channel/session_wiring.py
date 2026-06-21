from channels.session_channel.session_bot_manager import SessionBotManager
from channels.session_channel.session_channel import SessionChannel
from channels.session_channel.session_envelope_factory import SessionEnvelopeFactory
from channels.session_channel.session_message_processor import SessionMessageProcessor
from channels.session_channel.session_routing import SessionRouting
from channels.session_channel.session_transport import SessionTransport
from channels.session_channel.plugin_settings import SessionSettings
from src import pgmq

session_settings = SessionSettings()
session_bot_manager = SessionBotManager(
    session_settings.bots_config, session_settings.request_timeout_seconds
)
session_routing = SessionRouting(session_settings.bots_config)
session_transport = SessionTransport(session_bot_manager, session_settings.bot_source_name)
session_envelope_factory = SessionEnvelopeFactory(session_routing)
session_processor = SessionMessageProcessor(
    session_envelope_factory,
    session_settings,
    pgmq,
    session_settings.incoming_queue_name,
    session_settings.outgoing_queue_name,
)
session_channel = SessionChannel(
    session_bot_manager,
    session_routing,
    session_transport,
    session_processor,
)
