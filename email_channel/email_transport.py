from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid, formatdate
from typing import Any

import structlog

from email_channel.email_attachments import (
    prepare_attachments_data,
)
from email_channel.email_routing import EmailRouting
from email_channel.plugin_settings import MailboxConfig, EmailSettings
from src import ChannelDeliveryResult, Envelope
from src.multichannel_gateway.core.exceptions import (
    FatalError,
    TransientError,
)

logger = structlog.get_logger(__name__)


class EmailTransport:
    """Handles sending messages to email users via SMTP."""

    def __init__(self, routing: EmailRouting, settings: EmailSettings) -> None:
        self._routing = routing
        self._settings = settings

    async def send_to_email_user(
        self, message: dict[str, Any]
    ) -> ChannelDeliveryResult:
        """Facade method to send message to email user."""

        envelope = Envelope.model_validate(message)
        connector_id = envelope.connector_id
        mailbox_cfg = self._routing.get_mailbox_by_connector_id(connector_id)

        recipient = envelope.sender["external_id"]
        text = str(envelope.payload.get("text") or "").strip()
        subject = str(envelope.payload.get("subject") or "").strip()
        attachments = envelope.payload.get("attachments", [])

        attachments_data = await prepare_attachments_data(attachments)

        msg = self._build_email(
            from_addr=mailbox_cfg.smtp.smtp_from,
            to_addr=recipient,
            subject=subject,
            text=text,
            attachments_data=attachments_data,
        )

        return await self._send_with_error_handling(mailbox_cfg, msg, recipient)

    async def _send_with_error_handling(
        self, mailbox_cfg: MailboxConfig, msg: EmailMessage, recipient: str
    ) -> ChannelDeliveryResult:
        """Send email with error handling."""

        try:
            await asyncio.to_thread(self._send_smtp, mailbox_cfg, msg, recipient)
            return ChannelDeliveryResult(ok=True, external_id="")
        except Exception as exc:
            self._handle_errors(exc)
            raise  # pragma: no cover # _handle_errors always raises, but keep for clarity

    @staticmethod
    def _handle_errors(exc: Exception) -> None:
        """Handle SMTP and network errors."""

        if isinstance(exc, smtplib.SMTPRecipientsRefused):
            raise FatalError(
                f"Email delivery failure - recipient refused: {repr(exc)}"
            ) from exc
        if isinstance(exc, smtplib.SMTPAuthenticationError):
            raise FatalError(
                f"Email delivery failure - authentication: {repr(exc)}"
            ) from exc
        if isinstance(exc, smtplib.SMTPDataError):
            smtp_code = exc.smtp_code
            if smtp_code and 400 <= smtp_code < 500:
                raise TransientError(
                    f"Email transient delivery failure (SMTP {smtp_code}): {repr(exc)}"
                ) from exc
            raise FatalError(
                f"Email delivery failure (SMTP {smtp_code}): {repr(exc)}"
            ) from exc
        if isinstance(exc, smtplib.SMTPServerDisconnected):
            raise TransientError(
                f"Email transient delivery failure: {repr(exc)}"
            ) from exc
        if isinstance(exc, smtplib.SMTPException):
            raise FatalError(f"Email delivery failure: {repr(exc)}") from exc
        if isinstance(exc, (TimeoutError, OSError)):
            raise TransientError(
                f"Email transient delivery failure: {repr(exc)}"
            ) from exc
        raise FatalError(f"Email delivery failure: {repr(exc)}") from exc

    def _build_email(
        self,
        from_addr: str,
        to_addr: str,
        subject: str,
        text: str,
        attachments_data: list[tuple[bytes, str, str, int | None]] | None = None,
    ) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg["Date"] = formatdate()
        msg["Message-ID"] = make_msgid()

        msg.set_content(text)

        if attachments_data:
            for file_data, filename, mime_type, size in attachments_data:
                if len(file_data) > self._settings.channel_upload_max_mb * 1024 * 1024:
                    logger.error(
                        "Attachment exceeds size limit, skipping",
                        filename=filename,
                        size=len(file_data),
                    )
                    continue

                msg.add_attachment(
                    file_data,
                    filename=filename,
                    maintype=mime_type.split("/")[0]
                    if "/" in mime_type
                    else "application",
                    subtype=mime_type.split("/")[1]
                    if "/" in mime_type
                    else "octet-stream",
                )

        return msg

    @staticmethod
    def _send_smtp(
        mailbox_cfg: MailboxConfig,
        msg: EmailMessage,
        recipient: str,
    ) -> None:
        smtp_cfg = mailbox_cfg.smtp
        context = ssl.create_default_context()
        password = smtp_cfg.smtp_password
        assert password is not None  # Set by MailboxConfig validator

        with smtplib.SMTP(smtp_cfg.smtp_host, smtp_cfg.smtp_port) as server:
            server.starttls(context=context)
            server.login(smtp_cfg.smtp_username, password)
            server.sendmail(
                from_addr=mailbox_cfg.smtp.smtp_from,
                to_addrs=[recipient],
                msg=msg.as_string(),
            )
