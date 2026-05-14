import pytest

from channels.email_channel import (
    EmailChannel,
    EmailImapWatcher,
    EmailMessageProcessor,
    EmailRouting,
)
from channels.email_channel.plugin_settings import EmailSettings, MailboxConfig


@pytest.mark.asyncio
async def test_email_channel_build_channel_message_returns_envelope(
    settings: EmailSettings,
    routing: EmailRouting,
    processor: EmailMessageProcessor,
    watcher: EmailImapWatcher,
    mailbox: MailboxConfig,
    channel: EmailChannel,
) -> None:
    idempotency_key, envelope = await channel.build_channel_message(
        {
            "channel": "email",
            "connector_id": mailbox.connector_id,
            "uid": 42,
            "uidvalidity": 777,
            "message_id": "<abc@example.com>",
            "subject": "Hello",
            "text": "World",
            "sender": {"email": mailbox.imap_username},
        }
    )

    assert idempotency_key == envelope.idem_key
    assert envelope.channel == "email"
    assert envelope.connector_id == mailbox.connector_id
    assert envelope.cw_account_id == mailbox.cw_account_id
