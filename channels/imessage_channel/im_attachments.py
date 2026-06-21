from __future__ import annotations

import base64
from typing import Any

import structlog

from channels.imessage_channel.im_bot_manager import (
    BlueBubblesAPIError,
    IMessageBotManager,
)
from channels.imessage_channel.plugin_settings import IMessageSettings
from src.multichannel_gateway.core.attachment_models import Base64Attachment

logger = structlog.get_logger(__name__)


def _safe_int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _classify_file_type(mime_type: str) -> str:
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("audio/"):
        return "audio"
    return "file"


def extract_imessage_attachments(raw_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract BlueBubbles attachment metadata from a webhook payload.

    Unlike Telegram, which splits media into separate top-level fields
    (photo/video/voice/document/...), BlueBubbles puts every attachment —
    regardless of media type — in a single `attachments` list on the
    message, each carrying its own `mimeType`. So file-type classification
    happens by inspecting the mime type rather than which field was present.
    """

    message = raw_data.get("data", {})
    attachments: list[dict[str, Any]] = []

    for attachment in message.get("attachments") or []:
        mime_type = attachment.get("mimeType") or "application/octet-stream"
        attachments.append(
            {
                "source": "imessage",
                "file_type": _classify_file_type(mime_type),
                "file_id": attachment["guid"],
                "data_url": None,
                "filename": attachment.get("transferName", "attachment"),
                "mime_type": mime_type,
                "size": _safe_int(attachment.get("totalBytes")),
            }
        )

    return attachments


def is_over_size_limit(size_bytes: int | None, max_mb: int) -> bool:
    return False if size_bytes is None else size_bytes > (max_mb * 1024 * 1024)


async def download_imessage_attachment(
    bot_manager: IMessageBotManager, connector_id: str, attachment_guid: str
) -> bytes:
    """Download an attachment by GUID via BlueBubbles' download endpoint."""

    client = bot_manager.get_client_by_connector_id(connector_id)
    return await client.download_attachment(attachment_guid)


async def notify_imessage_user(
    bot_manager: IMessageBotManager,
    connector_id: str,
    chat_guid: str,
    text: str,
) -> None:
    """Send a user notification through the BlueBubbles REST API."""

    client = bot_manager.get_client_by_connector_id(connector_id)
    await client.send_text(chat_guid, text, temp_guid=f"notice-{chat_guid}")


def _resolve_attachment_file_metadata(
    attachment: dict[str, Any],
) -> tuple[str, str]:
    filename = attachment.get("filename") or "unknown"
    mime_type = attachment.get("mime_type") or "application/octet-stream"
    return filename, mime_type


async def _notify_attachment_too_large(
    bot_manager: IMessageBotManager,
    connector_id: str,
    chat_guid: str,
    settings: IMessageSettings,
) -> None:
    await notify_imessage_user(
        bot_manager,
        connector_id,
        chat_guid,
        settings.oversize_file_message,
    )


async def _prepare_single_imessage_to_chatwoot_attachment(
    attachment: dict[str, Any],
    *,
    bot_manager: IMessageBotManager,
    connector_id: str,
    chat_guid: str,
    settings: IMessageSettings,
) -> Base64Attachment | None:
    file_id = attachment.get("file_id")
    if not file_id:
        return None

    if is_over_size_limit(attachment.get("size"), settings.channel_upload_max_mb):
        await _notify_attachment_too_large(bot_manager, connector_id, chat_guid, settings)
        return None

    try:
        file_bytes = await download_imessage_attachment(
            bot_manager, connector_id, file_id
        )
    except BlueBubblesAPIError as exc:
        logger.warning(
            "Skipping unavailable BlueBubbles attachment",
            connector_id=connector_id,
            chat_guid=chat_guid,
            file_id=file_id,
            error=str(exc),
        )
        return None

    filename, mime_type = _resolve_attachment_file_metadata(attachment)

    if is_over_size_limit(len(file_bytes), settings.chatwoot_upload_max_mb):
        await _notify_attachment_too_large(bot_manager, connector_id, chat_guid, settings)
        return None

    return Base64Attachment(
        filename=filename,
        mime_type=mime_type,
        file_type=attachment.get("file_type", "file"),
        data=base64.b64encode(file_bytes).decode("ascii"),
        data_encoding="base64",
    )


async def prepare_imessage_to_chatwoot_attachments(
    message: dict[str, Any],
    *,
    bot_manager: IMessageBotManager,
    settings: IMessageSettings,
) -> dict[str, Any]:
    payload = dict(message.get("payload", {}))
    attachments = payload.get("attachments", [])
    if not attachments:
        return message

    prepared_attachments: list[Base64Attachment] = []

    for attachment in attachments:
        prepared_attachment = await _prepare_single_imessage_to_chatwoot_attachment(
            attachment,
            bot_manager=bot_manager,
            connector_id=str(message["connector_id"]),
            chat_guid=str(message["sender"]["external_id"]),
            settings=settings,
        )
        if prepared_attachment is not None:
            prepared_attachments.append(prepared_attachment)

    payload["attachments"] = prepared_attachments
    message["payload"] = payload
    return message
