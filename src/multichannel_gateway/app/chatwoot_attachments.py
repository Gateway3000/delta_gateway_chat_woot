from typing import Any


def _safe_int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def extract_chatwoot_attachments(raw_data: dict[str, Any]) -> list[dict[str, Any]]:
    attachments = raw_data.get("attachments", [])
    normalized: list[dict[str, Any]] = []

    for item in attachments:
        file_type = str(item.get("file_type", "file"))
        if file_type not in {"image", "video", "audio", "file"}:
            file_type = "file"

        normalized.append(
            {
                "source": "chatwoot",
                "file_type": file_type,
                "file_id": None,
                "data_url": item.get("data_url"),
                "filename": item.get("file_name") or item.get("filename"),
                "mime_type": item.get("content_type"),
                "size": _safe_int(item.get("file_size")),
            }
        )

    return normalized
