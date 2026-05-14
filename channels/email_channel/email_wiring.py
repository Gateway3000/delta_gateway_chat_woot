from channels.email_channel.email_channel import EmailChannel
from channels.email_channel.email_envelope_factory import EmailEnvelopeFactory
from channels.email_channel.email_imap_client import EmailImapClient
from channels.email_channel.email_imap_watcher import EmailImapWatcher
from channels.email_channel.email_message_processor import EmailMessageProcessor
from channels.email_channel.email_routing import EmailRouting
from channels.email_channel.email_transport import EmailTransport
from channels.email_channel.plugin_settings import EmailSettings
from src import pgmq

email_settings = EmailSettings()
email_routing = EmailRouting(email_settings.mailboxes_config)
email_envelope_factory = EmailEnvelopeFactory(email_routing)
email_imap_client = EmailImapClient(email_settings.mailboxes_config)
email_processor = EmailMessageProcessor(
    email_envelope_factory,
    email_imap_client,
    pgmq,
    email_settings.incoming_queue_name,
    email_settings.outgoing_queue_name,
)
email_imap_watcher = EmailImapWatcher(
    email_processor, email_settings.poll_interval_seconds
)
email_transport = EmailTransport(email_routing, email_settings)
email_channel = EmailChannel(
    email_routing,
    email_processor,
    email_imap_watcher,
    email_transport,
    email_imap_client,
)
