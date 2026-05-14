import smtplib
from email.message import EmailMessage
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from channels.email_channel import EmailTransport
from channels.email_channel.plugin_settings import EmailSettings, MailboxConfig
from src.multichannel_gateway.core.exceptions import (
    FatalError,
    TransientError,
)


def _make_message(
    mailbox: MailboxConfig, text: str = "Hello", subject: str = "Test"
) -> dict[str, Any]:
    return {
        "idem_key": "key-1",
        "channel": "email",
        "from_": "chatwoot",
        "to": "email",
        "connector_id": mailbox.connector_id,
        "cw_account_id": mailbox.cw_account_id,
        "cw_inbox_id": mailbox.cw_inbox_id,
        "message_id": "123",
        "sender": {"external_id": "user@example.com"},
        "payload": {"text": text, "subject": subject},
        "ts": 1.0,
    }


class TestEmailTransport:
    def test_build_email_text_only(
        self,
        settings: EmailSettings,
        transport: EmailTransport,
    ) -> None:
        mailbox = settings.mailboxes_config[0]
        msg = transport._build_email(
            from_addr=mailbox.smtp.smtp_from,
            to_addr="user@example.com",
            subject="Test",
            text="Hello",
        )

        assert msg["From"] == mailbox.smtp.smtp_from
        assert msg["To"] == "user@example.com"
        assert msg["Subject"] == "Test"
        assert "Message-ID" in msg

    @pytest.mark.asyncio
    async def test_send_to_email_user_returns_result_on_success(
        self,
        settings: EmailSettings,
        transport: EmailTransport,
    ) -> None:
        mailbox = settings.mailboxes_config[0]
        message = _make_message(mailbox)

        with patch("channels.email_channel.email_transport.smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = await transport.send_to_email_user(message)

            assert result.ok is True
            mock_server.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_to_email_user_raises_transient_on_connection_error(
        self,
        settings: EmailSettings,
        transport: EmailTransport,
    ) -> None:
        mailbox = settings.mailboxes_config[0]
        message = _make_message(mailbox)

        with patch("channels.email_channel.email_transport.smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = ConnectionRefusedError("Connection refused")

            with pytest.raises(TransientError):
                await transport.send_to_email_user(message)

    @pytest.mark.asyncio
    async def test_send_to_email_user_raises_fatal_on_auth_error(
        self,
        settings: EmailSettings,
        transport: EmailTransport,
    ) -> None:
        mailbox = settings.mailboxes_config[0]
        message = _make_message(mailbox)

        with patch("channels.email_channel.email_transport.smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = smtplib.SMTPAuthenticationError(
                535, b"Authentication failed"
            )

            with pytest.raises(FatalError):
                await transport.send_to_email_user(message)

    @pytest.mark.asyncio
    async def test_send_to_email_user_raises_fatal_on_recipient_refused(
        self,
        settings: EmailSettings,
        transport: EmailTransport,
    ) -> None:
        mailbox = settings.mailboxes_config[0]
        message = _make_message(mailbox)

        with patch("channels.email_channel.email_transport.smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_server.sendmail.side_effect = smtplib.SMTPRecipientsRefused(
                {"user@example.com": (550, b"User unknown")}
            )
            mock_smtp.return_value.__enter__.return_value = mock_server

            with pytest.raises(FatalError):
                await transport.send_to_email_user(message)

    @pytest.mark.asyncio
    async def test_send_to_email_user_raises_transient_on_smtp_data_error_4xx(
        self, transport: EmailTransport, mailbox: MailboxConfig
    ) -> None:
        message = _make_message(mailbox)

        with patch("channels.email_channel.email_transport.smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = smtplib.SMTPDataError(450, b"Temporary failure")

            with pytest.raises(TransientError):
                await transport.send_to_email_user(message)

    @pytest.mark.asyncio
    async def test_send_to_email_user_raises_fatal_on_smtp_data_error_5xx(
        self, transport: EmailTransport, mailbox: MailboxConfig
    ) -> None:
        message = _make_message(mailbox)

        with patch("channels.email_channel.email_transport.smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = smtplib.SMTPDataError(554, b"Transaction failed")

            with pytest.raises(FatalError):
                await transport.send_to_email_user(message)

    @pytest.mark.asyncio
    async def test_send_to_email_user_raises_transient_on_server_disconnected(
        self, transport: EmailTransport, mailbox: MailboxConfig
    ) -> None:
        message = _make_message(mailbox)

        with patch("channels.email_channel.email_transport.smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = smtplib.SMTPServerDisconnected("Disconnected")

            with pytest.raises(TransientError):
                await transport.send_to_email_user(message)

    @pytest.mark.asyncio
    async def test_send_to_email_user_raises_fatal_on_smtp_exception(
        self, transport: EmailTransport, mailbox: MailboxConfig
    ) -> None:
        message = _make_message(mailbox)

        with patch("channels.email_channel.email_transport.smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = smtplib.SMTPException("Generic error")

            with pytest.raises(FatalError):
                await transport.send_to_email_user(message)

    @pytest.mark.asyncio
    async def test_send_to_email_user_raises_transient_on_os_error(
        self, transport: EmailTransport, mailbox: MailboxConfig
    ) -> None:
        message = _make_message(mailbox)

        with patch("channels.email_channel.email_transport.smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = OSError("Network error")

            with pytest.raises(TransientError):
                await transport.send_to_email_user(message)

    @pytest.mark.asyncio
    async def test_send_to_email_user_raises_fatal_on_generic_exception(
        self, transport: EmailTransport, mailbox: MailboxConfig
    ) -> None:
        message = _make_message(mailbox)

        with patch("channels.email_channel.email_transport.smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = Exception("Generic failure")

            with pytest.raises(FatalError):
                await transport.send_to_email_user(message)

    def test_build_email_with_attachments(
        self, transport: EmailTransport, mailbox: MailboxConfig
    ) -> None:
        attachments_data: list[tuple[bytes, str, str, int | None]] = [
            (b"test data", "test.txt", "text/plain", 9),
        ]

        msg = transport._build_email(
            from_addr=mailbox.smtp.smtp_from,
            to_addr="user@example.com",
            subject="Test",
            text="Hello",
            attachments_data=attachments_data,
        )

        assert msg["From"] == mailbox.smtp.smtp_from
        payload = msg.get_payload()
        assert isinstance(payload, list)
        assert len(payload) == 2  # text + attachment
        # Verify first part is text
        assert isinstance(payload[0], EmailMessage)
        assert payload[0].get_content_type() == "text/plain"
        # Verify second part is attachment
        assert isinstance(payload[1], EmailMessage)
        assert payload[1].get_content_disposition() == "attachment"

    def test_build_email_skips_attachment_exceeding_size_limit(
        self, settings: EmailSettings, transport: EmailTransport, mailbox: MailboxConfig
    ) -> None:
        settings.channel_upload_max_mb = 0
        large_data = b"x" * 1024
        attachments_data: list[tuple[bytes, str, str, int | None]] = [
            (large_data, "large.bin", "application/octet-stream", 1024),
        ]

        msg = transport._build_email(
            from_addr=mailbox.smtp.smtp_from,
            to_addr="user@example.com",
            subject="Test",
            text="Hello",
            attachments_data=attachments_data,
        )

        # When attachment is skipped, payload is just text string
        payload = msg.get_payload()
        assert isinstance(payload, str)
        assert "Hello" in payload

    def test_build_email_with_mime_type_parsing(
        self, transport: EmailTransport, mailbox: MailboxConfig
    ) -> None:
        attachments_data: list[tuple[bytes, str, str, int | None]] = [
            (b"PDF data", "doc.pdf", "application/pdf", 9),
        ]

        msg = transport._build_email(
            from_addr=mailbox.smtp.smtp_from,
            to_addr="user@example.com",
            subject="Test",
            text="Hello",
            attachments_data=attachments_data,
        )

        payload = msg.get_payload()
        assert isinstance(payload, list)
        # Find the attachment part
        attachment_part = None
        for part in payload:
            if (
                isinstance(part, EmailMessage)
                and part.get_content_disposition() == "attachment"
            ):
                attachment_part = part
                break
        assert attachment_part is not None
        assert attachment_part.get_content_type() == "application/pdf"
