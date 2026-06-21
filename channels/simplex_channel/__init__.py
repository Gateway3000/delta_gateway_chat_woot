from channels.simplex_channel.plugin_settings import SimplexSettings
from channels.simplex_channel.sx_bot_manager import SimplexBotManager
from channels.simplex_channel.sx_channel import SimplexChannel
from channels.simplex_channel.sx_envelope_factory import SimplexEnvelopeFactory
from channels.simplex_channel.sx_message_processor import SimplexMessageProcessor
from channels.simplex_channel.sx_receiver import SimplexReceiver
from channels.simplex_channel.sx_routing import SimplexRouting
from channels.simplex_channel.sx_transport import SimplexTransport
from src import pgmq

sx_settings = SimplexSettings()
sx_bot_manager = SimplexBotManager(
    sx_settings.bots_config,
    sx_settings.send_timeout,
    sx_settings.reconnect_delay,
)
sx_routing = SimplexRouting(sx_settings.bots_config)
sx_transport = SimplexTransport(sx_bot_manager)
sx_envelope_factory = SimplexEnvelopeFactory(sx_routing)
sx_receiver = SimplexReceiver(sx_bot_manager, sx_routing, sx_settings)
sx_processor = SimplexMessageProcessor(
    sx_bot_manager,
    sx_transport,
    sx_envelope_factory,
    sx_settings,
    pgmq,
    sx_settings.incoming_queue_name,
    sx_settings.outgoing_queue_name,
)
simplex_channel = SimplexChannel(
    sx_bot_manager,
    sx_routing,
    sx_transport,
    sx_processor,
    sx_receiver,
)
