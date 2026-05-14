from unittest.mock import AsyncMock, MagicMock

import pytest

from channels.email_channel import (
    EmailImapClient,
    EmailRouting,
    EmailTransport,
    EmailImapWatcher,
    EmailMessageProcessor,
    EmailEnvelopeFactory,
    EmailChannel,
)
from channels.email_channel.plugin_settings import EmailSettings, MailboxConfig
from src import PGMessageQueue


@pytest.fixture
def settings() -> EmailSettings:
    return EmailSettings()


@pytest.fixture
def routing(settings: EmailSettings) -> EmailRouting:
    return EmailRouting(settings.mailboxes_config)


@pytest.fixture
def mailbox(settings: EmailSettings) -> MailboxConfig:
    return settings.mailboxes_config[0]


@pytest.fixture
def imap_client(settings: EmailSettings) -> EmailImapClient:
    return EmailImapClient(settings.mailboxes_config)


@pytest.fixture
def transport(routing: EmailRouting, settings: EmailSettings) -> EmailTransport:
    return EmailTransport(routing, settings)


@pytest.fixture
def processor(
    routing: EmailRouting,
) -> EmailMessageProcessor:
    return EmailMessageProcessor(
        EmailEnvelopeFactory(routing),
        AsyncMock(spec=EmailImapClient),
        AsyncMock(spec=PGMessageQueue),
        "to_cw",
        "from_cw",
    )


@pytest.fixture
def mock_processor() -> MagicMock:
    proc = MagicMock()
    proc.poll_once = AsyncMock()
    return proc


@pytest.fixture
def watcher(mock_processor: MagicMock) -> EmailImapWatcher:
    return EmailImapWatcher(mock_processor, poll_interval_seconds=0.01)


@pytest.fixture
def factory(routing: EmailRouting) -> EmailEnvelopeFactory:
    return EmailEnvelopeFactory(routing)


@pytest.fixture
def channel(
    routing: EmailRouting,
    processor: EmailMessageProcessor,
    watcher: EmailImapWatcher,
    transport: EmailTransport,
    imap_client: EmailImapClient,
) -> EmailChannel:
    return EmailChannel(routing, processor, watcher, transport, imap_client)
