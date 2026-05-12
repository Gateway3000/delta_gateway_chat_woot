import pytest

from email_channel import EmailEnvelopeFactory, EmailRouting
from email_channel.plugin_settings import MailboxConfig


class TestEmailEnvelopeFactory:
    def test_parse_channel_request_builds_envelope(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        factory: EmailEnvelopeFactory,
    ) -> None:
        raw_data = {
            "uid": 42,
            "uidvalidity": 777,
            "message_id": "<abc@example.com>",
            "subject": "Hello",
            "text": "Plain text",
            "sender": {"email": mailbox.imap_username, "name": "John Doe"},
        }

        idem_key, envelope = factory.parse_channel_request(
            raw_data,
            connector_id=mailbox.connector_id,
            channel="email",
        )

        assert idem_key == envelope.idem_key
        assert envelope.channel == "email"
        assert envelope.to == "chatwoot"
        assert envelope.connector_id == mailbox.connector_id
        assert envelope.cw_account_id == mailbox.cw_account_id
        assert envelope.cw_inbox_id == mailbox.cw_inbox_id
        assert envelope.message_id == "<abc@example.com>"
        assert envelope.sender.external_id == mailbox.imap_username.lower()
        assert envelope.sender.nickname == "abc"
        assert envelope.payload["text"] == "Subject: Hello\n\nPlain text"
        assert f"email->chatwoot:{mailbox.connector_id}:INBOX:777:42:" in idem_key

    def test_parse_channel_request_requires_sender_email(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        factory: EmailEnvelopeFactory,
    ) -> None:
        with pytest.raises(ValueError, match="sender.email is required"):
            factory.parse_channel_request(
                {
                    "uid": 1,
                    "uidvalidity": 2,
                    "message_id": "<x@example.com>",
                    "sender": {},
                },
                connector_id=mailbox.connector_id,
                channel="email",
            )

    def test_parse_channel_request_missing_uid_raises(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        factory: EmailEnvelopeFactory,
    ) -> None:
        with pytest.raises(ValueError, match="Missing required key: uid"):
            factory.parse_channel_request(
                {
                    "uidvalidity": 2,
                    "message_id": "<x@example.com>",
                    "sender": {"email": "test@example.com"},
                },
                connector_id=mailbox.connector_id,
                channel="email",
            )

    def test_parse_channel_request_missing_uidvalidity_raises(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        factory: EmailEnvelopeFactory,
    ) -> None:
        with pytest.raises(ValueError, match="Missing required key: uidvalidity"):
            factory.parse_channel_request(
                {
                    "uid": 1,
                    "message_id": "<x@example.com>",
                    "sender": {"email": "test@example.com"},
                },
                connector_id=mailbox.connector_id,
                channel="email",
            )

    def test_parse_channel_request_fallback_message_id_from_uid(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        factory: EmailEnvelopeFactory,
    ) -> None:
        raw_data = {
            "uid": 123,
            "uidvalidity": 456,
            "sender": {"email": "test@example.com"},
        }

        _, envelope = factory.parse_channel_request(
            raw_data,
            connector_id=mailbox.connector_id,
            channel="email",
        )

        assert envelope.message_id == "uid:123"

    def test_parse_channel_request_sender_without_at(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        factory: EmailEnvelopeFactory,
    ) -> None:
        raw_data = {
            "uid": 1,
            "uidvalidity": 2,
            "sender": {"email": "localpart"},
        }

        _, envelope = factory.parse_channel_request(
            raw_data,
            connector_id=mailbox.connector_id,
            channel="email",
        )

        assert envelope.sender.nickname is None

    def test_parse_chatwoot_request_builds_envelope(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        factory: EmailEnvelopeFactory,
    ) -> None:
        raw_data = {
            "inbox": {"id": int(mailbox.cw_inbox_id)},
            "conversation": {
                "meta": {"sender": {"identifier": "user@example.com"}},
                "messages": [{"id": 999, "content": "Reply message"}],
            },
            "content": "Reply message",
            "subject": "Re: Hello",
        }

        idem_key, envelope = factory.parse_chatwoot_request(
            raw_data,
            cw_account_id=mailbox.cw_account_id,
            channel="email",
        )

        assert idem_key == envelope.idem_key
        assert envelope.channel == "email"
        assert envelope.from_ == "chatwoot"
        assert envelope.to == "email"
        assert envelope.connector_id == mailbox.connector_id
        assert envelope.cw_inbox_id == mailbox.cw_inbox_id
        assert envelope.cw_account_id == mailbox.cw_account_id
        assert envelope.message_id == "999"
        assert envelope.sender.external_id == "user@example.com"
        assert envelope.payload["subject"] == "Re: Hello"
        assert envelope.payload["text"] == "Reply message"

    def test_parse_chatwoot_request_idempotency_key_format(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        factory: EmailEnvelopeFactory,
    ) -> None:
        raw_data = {
            "inbox": {"id": int(mailbox.cw_inbox_id)},
            "conversation": {
                "meta": {"sender": {"identifier": "user@example.com"}},
                "messages": [{"id": 999, "content": "Reply"}],
            },
        }

        idem_key, _ = factory.parse_chatwoot_request(
            raw_data,
            cw_account_id=mailbox.cw_account_id,
            channel="email",
        )

        assert (
            idem_key == f"chatwoot->email:{mailbox.connector_id}:999:user@example.com"
        )

    def test_parse_chatwoot_request_with_attachments(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        factory: EmailEnvelopeFactory,
    ) -> None:
        raw_data = {
            "inbox": {"id": int(mailbox.cw_inbox_id)},
            "conversation": {
                "meta": {"sender": {"identifier": "user@example.com"}},
                "messages": [{"id": 999, "content": "Reply"}],
            },
            "attachments": [
                {
                    "file_type": "image",
                    "file_name": "test.png",
                    "data_url": "data:image/png;base64,abc",
                    "content_type": "image/png",
                    "file_size": 1024,
                }
            ],
        }

        _, envelope = factory.parse_chatwoot_request(
            raw_data,
            cw_account_id=mailbox.cw_account_id,
            channel="email",
        )

        assert len(envelope.payload["attachments"]) == 1
        assert envelope.payload["attachments"][0]["filename"] == "test.png"
        assert envelope.payload["attachments"][0]["source"] == "chatwoot"

    def test_parse_chatwoot_request_empty_subject_and_content(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        factory: EmailEnvelopeFactory,
    ) -> None:
        raw_data = {
            "inbox": {"id": int(mailbox.cw_inbox_id)},
            "conversation": {
                "meta": {"sender": {"identifier": "user@example.com"}},
                "messages": [{"id": 999, "content": ""}],
            },
        }

        _, envelope = factory.parse_chatwoot_request(
            raw_data,
            cw_account_id=mailbox.cw_account_id,
            channel="email",
        )

        assert envelope.payload["subject"] == ""
        assert envelope.payload["text"] == ""

    def test_parse_channel_request_missing_message_id_and_uid_raises(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        factory: EmailEnvelopeFactory,
    ) -> None:
        with pytest.raises(
            ValueError, match="Either message_id or uid must be present"
        ):
            factory.parse_channel_request(
                {
                    "uidvalidity": 2,
                    "sender": {"email": "test@example.com"},
                },
                connector_id=mailbox.connector_id,
                channel="email",
            )
