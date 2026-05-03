import imaplib
from unittest.mock import MagicMock, patch

import pytest

from email_channel.email_imap_client import EmailImapClient
from email_channel.plugin_settings import MailboxConfig


class TestImapClient:
    client = EmailImapClient([MagicMock()])
    mock_conn = MagicMock(spec=imaplib.IMAP4_SSL)

    def test_calls_uid_store(self) -> None:
        self.client._mark_seen(self.mock_conn, "1")
        self.mock_conn.uid.assert_called_once_with("store", "1", "+FLAGS", "\\Seen")

    def test_returns_empty_when_connection_fails(
        self, imap_client: EmailImapClient, mailbox: MailboxConfig
    ) -> None:
        with patch.object(imap_client, "_connect_with_retry", return_value=None):
            result = imap_client._fetch_messages(mailbox)
            assert result == []

    def test_returns_empty_when_search_fails(
        self, imap_client: EmailImapClient, mailbox: MailboxConfig
    ) -> None:
        mock_conn = MagicMock(spec=imaplib.IMAP4_SSL)
        mock_conn.uid.return_value = ("NO", [])
        with patch.object(imap_client, "_connect_with_retry", return_value=mock_conn):
            result = imap_client._fetch_messages(mailbox)
            assert result == []

    def test_returns_empty_when_no_messages(
        self, imap_client: EmailImapClient, mailbox: MailboxConfig
    ) -> None:
        mock_conn = MagicMock(spec=imaplib.IMAP4_SSL)
        mock_conn.uid.return_value = ("OK", [b""])
        with patch.object(imap_client, "_connect_with_retry", return_value=mock_conn):
            result = imap_client._fetch_messages(mailbox)
            assert result == []

    def test_fetches_messages_successfully(
        self, imap_client: EmailImapClient, mailbox: MailboxConfig
    ) -> None:
        mock_conn = MagicMock(spec=imaplib.IMAP4_SSL)
        mock_conn.uid.return_value = ("OK", [b"1 2"])
        with patch.object(imap_client, "_connect_with_retry", return_value=mock_conn):
            with patch.object(
                imap_client,
                "_fetch_single_message",
                side_effect=[{"uid": 1}, {"uid": 2}],
            ):
                result = imap_client._fetch_messages(mailbox)
                assert len(result) == 2
                assert result[0]["uid"] == 1
                assert result[1]["uid"] == 2

    def test_skips_failed_messages(
        self, imap_client: EmailImapClient, mailbox: MailboxConfig
    ) -> None:
        mock_conn = MagicMock(spec=imaplib.IMAP4_SSL)
        mock_conn.uid.return_value = ("OK", [b"1 2"])
        with patch.object(imap_client, "_connect_with_retry", return_value=mock_conn):
            with patch.object(
                imap_client,
                "_fetch_single_message",
                side_effect=[{"uid": 1}, Exception("parse error")],
            ):
                result = imap_client._fetch_messages(mailbox)
                assert len(result) == 1

    def test_returns_none_on_bad_status(self) -> None:
        self.mock_conn.uid.return_value = ("NO", [])
        with patch.object(self.client, "_get_uidvalidity", return_value="123"):
            result = self.client._fetch_single_message(self.mock_conn, b"1", "INBOX")
            assert result is None

    def test_returns_none_when_raw_bytes_missing(self) -> None:
        self.mock_conn.uid.return_value = ("OK", [b"data"])
        with patch.object(self.client, "_get_uidvalidity", return_value="123"):
            result = self.client._fetch_single_message(self.mock_conn, b"1", "INBOX")
            assert result is None

    def test_builds_dict_on_success(self) -> None:
        self.mock_conn.uid.return_value = ("OK", [(None, b"raw_email_bytes")])
        with patch.object(self.client, "_get_uidvalidity", return_value="123"):
            with patch(
                "email_channel.email_imap_client.EmailMimeParser"
            ) as mock_parser:
                mock_parsed = MagicMock()
                mock_parsed.date = None
                mock_parsed.message_id = "<test@example.com>"
                mock_parsed.subject = "Test"
                mock_parsed.text_body = "Hello"
                mock_parsed.html_body = None
                mock_parsed.from_email = "sender@test.com"
                mock_parsed.from_name = "Sender"
                mock_parsed.attachments = []
                mock_parsed.raw_headers = {}
                mock_parsed.references = None
                mock_parsed.in_reply_to = None
                mock_parser.parse_raw_email.return_value = mock_parsed

                result = self.client._fetch_single_message(
                    self.mock_conn, b"1", "INBOX"
                )

                assert result is not None
                assert result["uid"] == 1
                assert result["message_id"] == "<test@example.com>"
                assert result["subject"] == "Test"
                assert result["sender"]["email"] == "sender@test.com"

    def test_returns_validity_on_ok(self) -> None:
        self.mock_conn.status.return_value = ("OK", [b"INBOX (UIDVALIDITY 777)"])
        result = self.client._get_uidvalidity(self.mock_conn, "INBOX")
        assert result == " 777"

    def test_returns_zero_on_no_uidvalidity(self) -> None:
        self.mock_conn.status.return_value = ("OK", [b"INBOX (FLAGS (\\Seen))"])
        result = self.client._get_uidvalidity(self.mock_conn, "INBOX")
        assert result == "0"

    def test_returns_zero_on_not_ok(self) -> None:
        self.mock_conn.status.return_value = ("NO", [])
        result = self.client._get_uidvalidity(self.mock_conn, "INBOX")
        assert result == "0"

    def test_builds_normalized_dict(self) -> None:
        raw = {
            "sender": {"email": "a@test.com", "name": "A"},
            "uid": "42",
            "uidvalidity": "777",
            "message_id": "<abc@example.com>",
            "subject": "Hello",
            "text": "World",
            "attachments": [],
            "raw_headers": {},
            "ts": 1.0,
        }
        result = EmailImapClient.normalize_imap_message("c1", raw)
        assert result["channel"] == "email"
        assert result["connector_id"] == "c1"
        assert result["uid"] == 42
        assert result["uidvalidity"] == 777
        assert result["sender"]["email"] == "a@test.com"

    def test_raises_on_missing_sender_email(self) -> None:
        raw = {"sender": {}, "uid": 1, "uidvalidity": 2}
        with pytest.raises(ValueError, match="sender.email is required"):
            EmailImapClient.normalize_imap_message("c1", raw)

    def test_raises_on_missing_uid(self) -> None:
        raw = {"sender": {"email": "a@test.com"}, "uidvalidity": 2}
        with pytest.raises(ValueError, match="uid is required"):
            EmailImapClient.normalize_imap_message("c1", raw)

    def test_raises_on_missing_uidvalidity(self) -> None:
        raw = {"sender": {"email": "a@test.com"}, "uid": 1}
        with pytest.raises(ValueError, match="uidvalidity is required"):
            EmailImapClient.normalize_imap_message("c1", raw)

    @pytest.mark.asyncio
    async def test_returns_payloads(
        self, imap_client: EmailImapClient, mailbox: MailboxConfig
    ) -> None:
        with patch.object(imap_client, "_fetch_messages", return_value=[{"uid": 1}]):
            with patch.object(
                EmailImapClient,
                "normalize_imap_message",
                return_value={"channel": "email"},
            ):
                result = await imap_client.fetch_inbound_payloads()
                assert len(result) == 1
                assert result[0]["channel"] == "email"

    @pytest.mark.asyncio
    async def test_handles_exceptions(
        self, imap_client: EmailImapClient, mailbox: MailboxConfig
    ) -> None:
        with patch.object(
            imap_client, "_fetch_messages", side_effect=Exception("boom")
        ):
            result = await imap_client.fetch_inbound_payloads()
            assert result == []

    def test_returns_connection_on_success(self, mailbox: MailboxConfig) -> None:
        with patch("email_channel.email_imap_client.imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_imap.return_value = mock_conn
            result = EmailImapClient._connect_with_retry(mailbox)
            assert result == mock_conn

    def test_returns_none_after_retries(self, mailbox: MailboxConfig) -> None:
        with patch("email_channel.email_imap_client.imaplib.IMAP4_SSL") as mock_imap:
            mock_imap.side_effect = Exception("connection refused")
            with patch("email_channel.email_imap_client.time.sleep"):
                result = EmailImapClient._connect_with_retry(mailbox)
                assert result is None

    def test_validate_connections_empty_config(self) -> None:
        client = EmailImapClient([])
        client.validate_connections()

    def test_validate_connections_success(self, imap_client: EmailImapClient) -> None:
        with patch("email_channel.email_imap_client.imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_imap.return_value = mock_conn
            imap_client.validate_connections()
            mock_conn.login.assert_called_once()
            mock_conn.logout.assert_called_once()

    def test_validate_connections_raises_on_imap_error(
        self, imap_client: EmailImapClient
    ) -> None:
        with patch("email_channel.email_imap_client.imaplib.IMAP4_SSL") as mock_imap:
            mock_conn = MagicMock()
            mock_conn.login.side_effect = imaplib.IMAP4.error("auth failed")
            mock_imap.return_value = mock_conn
            with pytest.raises(ConnectionError, match="Invalid IMAP credentials"):
                imap_client.validate_connections()
