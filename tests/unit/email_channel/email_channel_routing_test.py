import pytest

from channels.email_channel import (
    EmailChannel,
    EmailImapWatcher,
    EmailMessageProcessor,
    EmailRouting,
)
from channels.email_channel.plugin_settings import EmailSettings, MailboxConfig
from src import ConnectorNotFoundError


class TestEmailRouting:
    def test_email_channel_exposes_email_channel_name(
        self,
        settings: EmailSettings,
        routing: EmailRouting,
        processor: EmailMessageProcessor,
        watcher: EmailImapWatcher,
        channel: EmailChannel,
    ) -> None:
        assert channel.channel == "email"

    def test_email_routing_resolves_public_route_without_secrets(
        self, settings: EmailSettings, routing: EmailRouting, mailbox: MailboxConfig
    ) -> None:
        route = routing.get_route_by_connector_id(mailbox.connector_id)

        assert route == {
            "connector_id": mailbox.connector_id,
            "cw_account_id": mailbox.cw_account_id,
            "cw_inbox_id": mailbox.cw_inbox_id,
            "imap_mailbox": "INBOX",
            "smtp_from": mailbox.smtp.smtp_from,
        }
        assert "imap_password" not in route
        assert "smtp_password" not in route

    def test_email_routing_resolves_route_by_chatwoot_inbox(
        self, settings: EmailSettings, routing: EmailRouting, mailbox: MailboxConfig
    ) -> None:
        route = routing.get_route_by_inbox_id(mailbox.cw_inbox_id)
        assert route["connector_id"] == mailbox.connector_id

    def test_email_routing_rejects_unknown_connector(
        self, settings: EmailSettings, routing: EmailRouting
    ) -> None:
        with pytest.raises(ConnectorNotFoundError):
            routing.get_route_by_connector_id("missing")

    def test_email_routing_rejects_unknown_inbox(
        self, settings: EmailSettings, routing: EmailRouting
    ) -> None:
        with pytest.raises(ConnectorNotFoundError):
            routing.get_route_by_inbox_id("missing")
