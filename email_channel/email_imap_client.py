import asyncio
import contextlib
import imaplib
import time
from datetime import datetime, timezone
from typing import Any

import structlog

from email_channel.email_mime_parser import EmailMimeParser, ParsedEmail
from email_channel.plugin_settings import MailboxConfig

logger = structlog.get_logger(__name__)

MAX_CONNECTION_RETRIES = 5
RETRY_DELAY_SECONDS = 60


class EmailImapClient:
    """Provider-agnostic IMAP client facade for inbound payload polling."""

    def __init__(self, mailboxes_config: list[MailboxConfig]) -> None:
        self._mailboxes_config = mailboxes_config

    async def fetch_inbound_payloads(self) -> list[dict[str, Any]]:
        """Returns normalized inbound payloads for processor ingestion."""
        payloads: list[dict[str, Any]] = []

        for config in self._mailboxes_config:
            try:
                messages = await asyncio.to_thread(self._fetch_messages, config)
                payloads.extend(
                    self.normalize_imap_message(config.connector_id, msg_data)
                    for msg_data in messages
                )
            except Exception as exc:
                logger.error(
                    "IMAP fetch failed for connector",
                    connector_id=config.connector_id,
                    error=str(exc),
                )

        return payloads

    def _fetch_messages(self, config: MailboxConfig) -> list[dict[str, Any]]:
        # sourcery skip: extract-method, use-named-expression
        conn = self._connect_with_retry(config)
        if conn is None:
            return []

        try:
            conn.select(config.imap_mailbox, readonly=False)
            status, data = conn.uid("SEARCH", "UNSEEN")
            if status != "OK" or not data[0]:
                return []

            message_uids = data[0].split()
            results: list[dict[str, Any]] = []

            for msg_uid in message_uids:
                try:
                    parsed = self._fetch_single_message(
                        conn, msg_uid, config.imap_mailbox
                    )
                    if parsed:
                        results.append(parsed)
                except Exception as exc:
                    logger.warning(
                        "Failed to parse message",
                        connector_id=config.connector_id,
                        message_uid=msg_uid.decode(),
                        error=str(exc),
                    )

            return results
        finally:
            with contextlib.suppress(Exception):
                conn.logout()

    def _fetch_single_message(
        self, conn: imaplib.IMAP4_SSL, msg_uid: bytes, mailbox: str
    ) -> dict[str, Any] | None:
        uid = int(msg_uid)
        uidvalidity = self._get_uidvalidity(conn, mailbox)

        status, data = conn.uid("fetch", msg_uid.decode(), "(RFC822)")
        if status != "OK":
            return None

        raw_bytes = data[0][1] if isinstance(data[0], tuple) else None
        if not isinstance(raw_bytes, bytes):
            return None

        parsed_email: ParsedEmail = EmailMimeParser.parse_raw_email(raw_bytes)

        self._mark_seen(conn, msg_uid.decode())

        ts = (
            parsed_email.date.timestamp()
            if parsed_email.date
            else datetime.now(tz=timezone.utc).timestamp()
        )

        return {
            "uid": uid,
            "uidvalidity": uidvalidity,
            "message_id": parsed_email.message_id,
            "subject": parsed_email.subject,
            "text": parsed_email.text_body,
            "html": parsed_email.html_body,
            "sender": {
                "email": parsed_email.from_email,
                "name": parsed_email.from_name,
            },
            "attachments": parsed_email.attachments,
            "raw_headers": parsed_email.raw_headers,
            "ts": ts,
            "references": parsed_email.references,
            "in_reply_to": parsed_email.in_reply_to,
        }

    @staticmethod
    def _connect_with_retry(config: MailboxConfig) -> imaplib.IMAP4_SSL | None:
        for attempt in range(1, MAX_CONNECTION_RETRIES + 1):
            try:
                conn = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
                conn.login(config.imap_username, config.imap_password)
                return conn
            except Exception as exc:
                logger.warning(
                    "IMAP connection attempt failed",
                    connector_id=config.connector_id,
                    attempt=attempt,
                    max_attempts=MAX_CONNECTION_RETRIES,
                    error=str(exc),
                )
                if attempt < MAX_CONNECTION_RETRIES:
                    time.sleep(RETRY_DELAY_SECONDS)

        logger.error(
            "IMAP connection failed after all retries",
            connector_id=config.connector_id,
            max_attempts=MAX_CONNECTION_RETRIES,
        )
        return None

    def validate_connections(self) -> None:
        """Validates IMAP connections for all configured mailboxes."""
        if not self._mailboxes_config:
            return
        for config in self._mailboxes_config:
            try:
                conn = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
                conn.login(config.imap_username, config.imap_password)
                conn.logout()
            except imaplib.IMAP4.error as e:
                error_msg = (
                    "Invalid IMAP credentials. Either provide valid credentials or disable Email channel in the "
                    "CHANNELS variable."
                )
                raise ConnectionError(error_msg) from e

    @staticmethod
    def _get_uidvalidity(conn: imaplib.IMAP4_SSL, mailbox: str) -> str:
        status, data = conn.status(mailbox, "(UIDVALIDITY)")
        if status == "OK":
            uidvalidity_str = data[0].decode()
            if "UIDVALIDITY" in uidvalidity_str:
                return uidvalidity_str.split("UIDVALIDITY")[-1].strip(")")
        return "0"

    @staticmethod
    def _mark_seen(conn: imaplib.IMAP4_SSL, msg_uid: str) -> None:
        conn.uid("store", msg_uid, "+FLAGS", "\\Seen")

    @staticmethod
    def normalize_imap_message(
        connector_id: str,
        raw_message: dict[str, Any],
        *,
        channel: str = "email",
    ) -> dict[str, Any]:
        """Normalizes IMAP-side payload to EmailMessageProcessor input contract."""

        sender = raw_message.get("sender", {})
        sender_email = str(sender.get("email") or "").strip()
        if not sender_email:
            raise ValueError("sender.email is required")

        uid = raw_message.get("uid")
        uidvalidity = raw_message.get("uidvalidity")
        if uid is None:
            raise ValueError("uid is required")
        if uidvalidity is None:
            raise ValueError("uidvalidity is required")

        return {
            "channel": channel,
            "connector_id": connector_id,
            "uid": int(uid),
            "uidvalidity": int(uidvalidity),
            "message_id": raw_message.get("message_id"),
            "subject": str(raw_message.get("subject") or ""),
            "text": str(raw_message.get("text") or ""),
            "sender": {
                "email": sender_email,
                "name": str(sender.get("name") or "").strip(),
            },
            "attachments": raw_message.get("attachments", []),
            "raw_headers": raw_message.get("raw_headers", {}),
            "ts": raw_message.get("ts"),
        }
