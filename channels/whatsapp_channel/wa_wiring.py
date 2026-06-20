from channels.whatsapp_channel.plugin_settings import WhatsAppSettings
from channels.whatsapp_channel.wa_channel import WhatsAppChannel
from channels.whatsapp_channel.wa_envelope_factory import WhatsAppEnvelopeFactory
from channels.whatsapp_channel.wa_message_processor import WhatsAppMessageProcessor
from channels.whatsapp_channel.wa_routing import WhatsAppRouting
from channels.whatsapp_channel.wa_transport import WhatsAppTransport
from src import pgmq

wa_settings = WhatsAppSettings()
wa_routing = WhatsAppRouting(wa_settings.whatsapp_config)
wa_envelope_factory = WhatsAppEnvelopeFactory(wa_routing)
wa_transport = WhatsAppTransport(wa_routing, wa_settings)
wa_processor = WhatsAppMessageProcessor(
    wa_envelope_factory,
    wa_settings,
    pgmq,
    wa_settings.incoming_queue_name,
    wa_settings.outgoing_queue_name,
)
whatsapp_channel = WhatsAppChannel(wa_routing, wa_transport, wa_processor)
