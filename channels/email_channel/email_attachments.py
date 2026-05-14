from __future__ import annotations

import mimetypes
import os
from typing import Any
from urllib.parse import urlparse

import aiohttp
import structlog

from src.multichannel_gateway.core.attachment_models import Base64Attachment

logger = structlog.get_logger(__name__)


async def download_attachment(url: str) -> bytes | None:
    """Download file from URL using aiohttp with proper redirect handling."""

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status == 200:
                    return await resp.read()
                logger.error(
                    "Attachment download failed",
                    url=url,
                    status=resp.status,
                )
                return None
    except Exception as exc:
        logger.error(
            "Error downloading attachment",
            url=url,
            error=str(exc),
        )
        return None


def extract_filename_from_url(url: str) -> str | None:
    """Extract filename from URL path."""

    if not url:
        return None
    parsed = urlparse(url)
    basename = os.path.basename(parsed.path)
    return basename if basename and "." in basename else None


def get_extension_from_mime(mime_type: str) -> str:
    """Get file extension from MIME type."""

    mime_to_ext = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "audio/mpeg": ".mp3",
        "audio/ogg": ".ogg",
    }
    if mime_type in mime_to_ext:
        return mime_to_ext[mime_type]
    ext = mimetypes.guess_extension(mime_type)
    return ext or ""


def normalize_filename(attachment: dict[str, Any]) -> str:
    """Get filename from attachment with fallback to URL, then add extension."""

    data_url = attachment.get("data_url", "")
    filename = extract_filename_from_url(data_url)

    if not filename:
        filename = "file"

    if "." not in filename:
        mime_type = attachment.get("mime_type", "")
        if ext := get_extension_from_mime(mime_type):
            filename = f"{filename}{ext}"

    return filename


async def prepare_attachments_data(
    attachments: list[dict[str, Any]],
) -> list[tuple[bytes, str, str, int | None]]:
    """Download and prepare attachments data."""
    attachments_data: list[tuple[bytes, str, str, int | None]] = []
    for attachment in attachments:
        data_url = attachment.get("data_url")
        if not data_url:
            continue

        file_data = await download_attachment(data_url)
        if file_data is None:
            continue

        filename = normalize_filename(attachment)
        mime_type = attachment.get("mime_type") or "application/octet-stream"
        attachments_data.append(
            (file_data, filename, mime_type, attachment.get("size"))
        )

    return attachments_data


def _resolve_attachment_metadata(attachment: dict[str, Any]) -> tuple[str, str]:
    filename = attachment.get("filename") or "attachment"
    mime_type = attachment.get("content_type") or "application/octet-stream"
    return filename, mime_type


def prepare_email_to_chatwoot_attachments(
    message: dict[str, Any],
) -> dict[str, Any]:
    """Convert email attachments from base64 dicts to Base64Attachment objects."""

    payload = dict(message.get("payload", {}))
    attachments = payload.get("attachments", [])
    if not attachments:
        return message

    prepared_attachments: list[Base64Attachment] = []

    for attachment in attachments:
        data = attachment.get("data")
        if not data:
            continue

        filename, mime_type = _resolve_attachment_metadata(attachment)

        prepared_attachment = Base64Attachment(
            filename=filename,
            mime_type=mime_type,
            file_type=attachment.get("file_type", "file"),
            data=data,
            data_encoding=attachment.get("data_encoding", "base64"),
        )
        prepared_attachments.append(prepared_attachment)

    payload["attachments"] = prepared_attachments
    message["payload"] = payload
    return message
