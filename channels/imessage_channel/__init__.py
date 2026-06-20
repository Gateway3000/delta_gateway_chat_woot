from channels.imessage_channel.plugin_settings import IMessageSettings
from channels.imessage_channel.im_bot_manager import IMessageBotManager
from channels.imessage_channel.im_channel import IMessageChannel
from channels.imessage_channel.im_envelope_factory import IMessageEnvelopeFactory
from channels.imessage_channel.im_message_processor import IMessageMessageProcessor
from channels.imessage_channel.im_routing import IMessageRouting
from channels.imessage_channel.im_transport import IMessageTransport
from channels.imessage_channel.im_wh_manager import IMessageWebhookManager
from src import pgmq

im_settings = IMessageSettings()
im_bot_manager = IMessageBotManager(im_settings.bots_config)
im_routing = IMessageRouting(im_settings.bots_config)
im_webhooks = IMessageWebhookManager(
    im_settings.wh_domain,
    [cfg.connector_id for cfg in im_settings.bots_config],
    im_settings,
    im_bot_manager,
)
im_transport = IMessageTransport(im_bot_manager)
im_envelope_factory = IMessageEnvelopeFactory(im_routing)
im_processor = IMessageMessageProcessor(
    im_bot_manager,
    im_transport,
    im_envelope_factory,
    im_settings,
    pgmq,
    im_settings.incoming_queue_name,
    im_settings.outgoing_queue_name,
)
imessage_channel = IMessageChannel(
    im_bot_manager,
    im_routing,
    im_transport,
    im_processor,
    im_webhooks,
)

