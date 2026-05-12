from __future__ import annotations

import base64
import logging
import re
from datetime import datetime
from email import policy, utils, message_from_bytes
from email.header import decode_header
from email.message import Message
from typing import Any, cast

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ParsedEmail(BaseModel):
    """Holds all extracted fields from a raw RFC822 email."""

    message_id: str = ""
    from_email: str = ""
    from_name: str = ""
    to: str = ""
    subject: str = ""
    date: datetime | None = None
    text_body: str = ""
    html_body: str = ""
    references: str = ""
    in_reply_to: str = ""
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    raw_headers: dict[str, str] = Field(default_factory=dict)


class EmailMimeParser:
    """Parses raw RFC822 email bytes into a structured ParsedEmail."""

    @staticmethod
    def parse_raw_email(raw_bytes: bytes) -> ParsedEmail:
        msg = message_from_bytes(raw_bytes, policy=policy.default)
        parsed = ParsedEmail()

        parsed.message_id = msg.get("Message-ID", "").strip()
        parsed.from_email, parsed.from_name = EmailMimeParser._parse_address(
            msg.get("From", "")
        )
        parsed.to = msg.get("To", "").strip()
        parsed.subject = EmailMimeParser._decode_header_value(msg.get("Subject", ""))
        parsed.references = msg.get("References", "").strip()
        parsed.in_reply_to = msg.get("In-Reply-To", "").strip()

        if date_str := msg.get("Date"):
            try:
                parsed.date = utils.parsedate_to_datetime(date_str)
            except Exception:
                parsed.date = None

        EmailMimeParser._extract_bodies(msg, parsed)
        EmailMimeParser._extract_attachments(msg, parsed)
        EmailMimeParser._capture_raw_headers(msg, parsed)

        return parsed

    @staticmethod
    def _parse_address(header_value: str) -> tuple[str, str]:
        if not header_value:
            return "", ""

        header_value = header_value.strip()
        if match := re.match(r"^(.*?)\s*<([^>]+)>$", header_value):
            name = match[1].strip().strip('"')
            email_addr = match[2].strip()
            return email_addr, name

        if "@" in header_value:
            return header_value.strip(), ""

        return "", header_value.strip()

    @staticmethod
    def _decode_header_value(value: str | None) -> str:
        if not value:
            return ""

        decoded_parts = decode_header(value)
        result = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                result.append(part)
        return "".join(result).strip()

    @staticmethod
    def _extract_bodies(msg: Message, parsed: ParsedEmail) -> None:
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition:
                    continue

                if content_type == "text/plain" and not parsed.text_body:
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        charset = part.get_content_charset() or "utf-8"
                        parsed.text_body = payload.decode(charset, errors="replace")

                elif content_type == "text/html" and not parsed.html_body:
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        charset = part.get_content_charset() or "utf-8"
                        parsed.html_body = payload.decode(charset, errors="replace")
        else:
            content_type = msg.get_content_type()
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                charset = msg.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
                if content_type == "text/plain":
                    parsed.text_body = decoded
                elif content_type == "text/html":
                    parsed.html_body = decoded

    @staticmethod
    def _extract_attachments(msg: Message, parsed: ParsedEmail) -> None:
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" not in content_disposition:
                continue

            filename = part.get_filename()
            if not filename:
                continue

            payload = part.get_payload(decode=True)
            if not payload:
                continue

            content_type = part.get_content_type()
            size = len(payload)

            parsed.attachments.append(
                {
                    "filename": filename,
                    "content_type": content_type,
                    "size": size,
                    "data": base64.b64encode(cast(bytes, payload)).decode("ascii"),
                    "data_encoding": "base64",
                }
            )

    @staticmethod
    def _capture_raw_headers(msg: Message, parsed: ParsedEmail) -> None:
        for key, value in msg.items():
            if key.lower() not in (
                "message-id",
                "from",
                "to",
                "subject",
                "date",
                "references",
                "in-reply-to",
            ):
                parsed.raw_headers[key] = value
