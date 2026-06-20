from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from deltachat_rpc_client.const import ViewType

from src.multichannel_gateway.core.attachment_models import Base64Attachment


def _safe_int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def is_over_size_limit(size_bytes: int | None, max_mb: int) -> bool:
    return False if size_bytes is None else size_bytes > (max_mb * 1024 * 1024)


def _normalize_view_type(view_type: Any) -> str:
    if view_type is None:
        return ""
    return str(view_type).strip().lower()


def _classify_file_type(mime_type: str, view_type: Any = None) -> str:
    normalized_view_type = _normalize_view_type(view_type)
    if normalized_view_type in {"voice"}:
        return "audio"
    if normalized_view_type in {"image", "gif"}:
        return "image"
    if normalized_view_type == "video":
        return "video"
    if normalized_view_type == "audio":
        return "audio"

    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"
    return "file"


def _resolve_file_metadata(
    attachment: dict[str, Any],
    file_path: str,
) -> tuple[str, str, str, str]:
    filename = (
        attachment.get("filename")
        or attachment.get("file_name")
        or Path(file_path).name
        or "attachment"
    )
    mime_type = (
        attachment.get("mime_type")
        or attachment.get("mimeType")
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )
    view_type = attachment.get("view_type") or attachment.get("viewtype") or ""
    file_type = _classify_file_type(str(mime_type), view_type)
    return str(filename), str(mime_type), str(view_type or ""), file_type


def extract_delta_chat_attachments(raw_data: dict[str, Any]) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []

    attachment_list = raw_data.get("attachments") or []
    if attachment_list:
        for attachment in attachment_list:
            file_path = str(attachment.get("path") or attachment.get("file_path") or "")
            if not file_path:
                continue
            filename, mime_type, view_type, file_type = _resolve_file_metadata(
                attachment, file_path
            )
            attachments.append(
                {
                    "source": "deltachat",
                    "file_type": file_type,
                    "file_id": attachment.get("file_id") or file_path,
                    "data_url": None,
                    "path": file_path,
                    "file_path": file_path,
                    "filename": filename,
                    "mime_type": mime_type,
                    "view_type": view_type,
                    "size": _safe_int(attachment.get("size") or attachment.get("file_size")),
                }
            )
        return attachments

    file_path = str(raw_data.get("file") or raw_data.get("file_path") or "")
    if not file_path:
        return []

    filename, mime_type, view_type, file_type = _resolve_file_metadata(raw_data, file_path)
    return [
        {
            "source": "deltachat",
            "file_type": file_type,
            "file_id": raw_data.get("message_id") or file_path,
            "data_url": None,
            "path": file_path,
            "file_path": file_path,
            "filename": filename,
            "mime_type": mime_type,
            "view_type": view_type,
            "size": _safe_int(raw_data.get("size") or raw_data.get("file_size")),
        }
    ]


def prepare_delta_chat_to_chatwoot_attachments(
    attachments: list[dict[str, Any]],
    *,
    max_mb: int,
) -> list[Base64Attachment]:
    prepared: list[Base64Attachment] = []

    for attachment in attachments:
        file_path = str(attachment.get("path") or attachment.get("file_path") or "")
        if not file_path:
            continue

        path = Path(file_path)
        if not path.exists():
            continue

        size_bytes = attachment.get("size")
        if size_bytes is None:
            size_bytes = path.stat().st_size
        if is_over_size_limit(size_bytes, max_mb):
            continue

        filename = str(attachment.get("filename") or path.name or "attachment")
        mime_type = str(
            attachment.get("mime_type")
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        file_type = str(attachment.get("file_type") or _classify_file_type(mime_type))

        prepared.append(
            Base64Attachment(
                filename=filename,
                mime_type=mime_type,
                file_type=file_type,
                data=base64.b64encode(path.read_bytes()).decode("ascii"),
                data_encoding="base64",
            )
        )

    return prepared


def resolve_delta_chat_viewtype(attachment: dict[str, Any]) -> ViewType | None:
    normalized_view_type = _normalize_view_type(
        attachment.get("view_type") or attachment.get("viewtype")
    )
    if normalized_view_type == "image":
        return ViewType.IMAGE
    if normalized_view_type == "video":
        return ViewType.VIDEO
    if normalized_view_type == "audio":
        return ViewType.AUDIO
    if normalized_view_type == "voice":
        return ViewType.VOICE
    if normalized_view_type == "gif":
        return ViewType.GIF
    if normalized_view_type == "sticker":
        return ViewType.STICKER

    mime_type = str(attachment.get("mime_type") or attachment.get("mimeType") or "")
    if mime_type.startswith("image/"):
        return ViewType.IMAGE
    if mime_type.startswith("video/"):
        return ViewType.VIDEO
    if mime_type.startswith("audio/"):
        return ViewType.VOICE if normalized_view_type == "voice" else ViewType.AUDIO
    return None

