from email_channel.email_channel import EmailChannel
from email_channel.email_envelope_factory import EmailEnvelopeFactory
from email_channel.email_imap_client import EmailImapClient
from email_channel.email_imap_watcher import EmailImapWatcher
from email_channel.email_message_processor import EmailMessageProcessor
from email_channel.email_routing import EmailRouting
from email_channel.email_transport import EmailTransport
from email_channel.plugin_settings import EmailSettings
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
email_imap_watcher = EmailImapWatcher(email_processor)
email_transport = EmailTransport(email_routing, email_settings)
email_channel = EmailChannel(
    email_routing,
    email_processor,
    email_imap_watcher,
    email_transport,
)
