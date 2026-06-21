from __future__ import annotations

import mimetypes
from typing import Any


def _classify_file_type(mime_type: str) -> str:
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"
    return "file"


def build_inbound_chatwoot_attachments(
    attachments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert signal-bridge inbound attachments into Chatwoot Base64Attachments.

    The bridge downloads each attachment from Signal's CDN and delivers it with
    its bytes inline as base64 (`data`) plus `content_type`/`filename`/`size`.
    Chatwoot's delivery path accepts `Base64Attachment`-shaped dicts, so we
    reshape them here and let the Chatwoot client upload them.
    """
    prepared: list[dict[str, Any]] = []
    for attachment in attachments:
        data = attachment.get("data")
        if not data:
            continue
        filename = str(attachment.get("filename") or "attachment")
        mime_type = str(
            attachment.get("content_type")
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        prepared.append(
            {
                "kind": "base64",
                "filename": filename,
                "mime_type": mime_type,
                "file_type": _classify_file_type(mime_type),
                "data": data,
                "data_encoding": "base64",
            }
        )
    return prepared
