from channels.signal_channel.plugin_settings import SignalSettings
from channels.signal_channel.sig_bot_manager import SignalBotManager
from channels.signal_channel.sig_channel import SignalChannel
from channels.signal_channel.sig_envelope_factory import SignalEnvelopeFactory
from channels.signal_channel.sig_message_processor import SignalMessageProcessor
from channels.signal_channel.sig_receiver import SignalReceiver
from channels.signal_channel.sig_routing import SignalRouting
from channels.signal_channel.sig_transport import SignalTransport
from src import pgmq

sig_settings = SignalSettings()
sig_bot_manager = SignalBotManager(
    sig_settings.bots_config,
    sig_settings.send_timeout,
    sig_settings.reconnect_delay,
)
sig_routing = SignalRouting(sig_settings.bots_config)
sig_transport = SignalTransport(sig_bot_manager)
sig_envelope_factory = SignalEnvelopeFactory(sig_routing)
sig_receiver = SignalReceiver(sig_bot_manager, sig_routing, sig_settings)
sig_processor = SignalMessageProcessor(
    sig_bot_manager,
    sig_transport,
    sig_envelope_factory,
    sig_settings,
    pgmq,
    sig_settings.incoming_queue_name,
    sig_settings.outgoing_queue_name,
)
signal_channel = SignalChannel(
    sig_bot_manager,
    sig_routing,
    sig_transport,
    sig_processor,
    sig_receiver,
)
