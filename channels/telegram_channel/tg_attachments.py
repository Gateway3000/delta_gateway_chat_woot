from __future__ import annotations

import base64
import io
from typing import Any

import structlog
from aiogram.exceptions import TelegramBadRequest

from channels.telegram_channel.plugin_settings import TelegramSettings
from channels.telegram_channel.tg_bot_manager import TelegramBotManager
from src.multichannel_gateway.core.attachment_models import Base64Attachment

logger = structlog.get_logger(__name__)


def _safe_int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def extract_telegram_attachments(raw_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract Telegram attachment metadata from a Telegram -> Chatwoot update."""

    message = raw_data.get("message", {})
    attachments: list[dict[str, Any]] = []

    if message.get("photo"):
        photo = message["photo"][-1]
        attachments.append(
            {
                "source": "telegram",
                "file_type": "image",
                "file_id": photo["file_id"],
                "data_url": None,
                "filename": "photo.jpg",
                "mime_type": "image/jpeg",
                "size": _safe_int(photo.get("file_size")),
            }
        )

    if message.get("video"):
        video = message["video"]
        attachments.append(
            {
                "source": "telegram",
                "file_type": "video",
                "file_id": video["file_id"],
                "data_url": None,
                "filename": video.get("file_name", "video.mp4"),
                "mime_type": video.get("mime_type", "video/mp4"),
                "size": _safe_int(video.get("file_size")),
            }
        )

    if message.get("video_note"):
        video_note = message["video_note"]
        attachments.append(
            {
                "source": "telegram",
                "file_type": "video",
                "file_id": video_note["file_id"],
                "data_url": None,
                "filename": "video_note.mp4",
                "mime_type": "video/mp4",
                "size": _safe_int(video_note.get("file_size")),
            }
        )

    if message.get("audio"):
        audio = message["audio"]
        attachments.append(
            {
                "source": "telegram",
                "file_type": "audio",
                "file_id": audio["file_id"],
                "data_url": None,
                "filename": audio.get("file_name", "audio.mp3"),
                "mime_type": audio.get("mime_type", "audio/mpeg"),
                "size": _safe_int(audio.get("file_size")),
            }
        )

    if message.get("voice"):
        voice = message["voice"]
        attachments.append(
            {
                "source": "telegram",
                "file_type": "audio",
                "file_id": voice["file_id"],
                "data_url": None,
                "filename": "voice.ogg",
                "mime_type": voice.get("mime_type", "audio/ogg"),
                "size": _safe_int(voice.get("file_size")),
            }
        )

    if message.get("document"):
        document = message["document"]
        attachments.append(
            {
                "source": "telegram",
                "file_type": "file",
                "file_id": document["file_id"],
                "data_url": None,
                "filename": document.get("file_name", "document"),
                "mime_type": document.get("mime_type", "application/octet-stream"),
                "size": _safe_int(document.get("file_size")),
            }
        )

    if message.get("sticker"):
        sticker = message["sticker"]
        attachments.append(
            {
                "source": "telegram",
                "file_type": "image",
                "file_id": sticker["file_id"],
                "data_url": None,
                "filename": "sticker.webp",
                "mime_type": "image/webp",
                "size": _safe_int(sticker.get("file_size")),
            }
        )

    if message.get("animation"):
        animation = message["animation"]
        attachments.append(
            {
                "source": "telegram",
                "file_type": "image",
                "file_id": animation["file_id"],
                "data_url": None,
                "filename": animation.get("file_name", "animation.gif"),
                "mime_type": animation.get("mime_type", "image/gif"),
                "size": _safe_int(animation.get("file_size")),
            }
        )

    return attachments


def is_over_size_limit(size_bytes: int | None, max_mb: int) -> bool:
    return False if size_bytes is None else size_bytes > (max_mb * 1024 * 1024)


async def download_telegram_attachment(
    bot_manager: TelegramBotManager, connector_id: str, file_id: str
) -> bytes:
    """Download file by Telegram file_id. Returns file bytes."""

    bot = bot_manager.get_bot_by_connector_id(connector_id)
    telegram_file = await bot.get_file(file_id)
    file_path = telegram_file.file_path
    if not file_path:
        raise ValueError(f"Telegram file_path is empty for file_id={file_id}")

    buffer = io.BytesIO()
    await bot.download_file(file_path, destination=buffer)
    return buffer.getvalue()


async def notify_telegram_user(
    bot_manager: TelegramBotManager,
    connector_id: str,
    chat_id: str | int,
    text: str,
) -> None:
    """Send a user notification through Telegram Bot API."""

    bot = bot_manager.get_bot_by_connector_id(connector_id)
    await bot.send_message(chat_id=chat_id, text=text)


def _resolve_attachment_file_metadata(
    attachment: dict[str, Any],
) -> tuple[str, str]:
    filename = attachment.get("filename") or "unknown"
    mime_type = attachment.get("mime_type") or "application/octet-stream"
    return filename, mime_type


async def _notify_attachment_too_large(
    bot_manager: TelegramBotManager,
    connector_id: str,
    chat_id: str,
    settings: TelegramSettings,
) -> None:
    await notify_telegram_user(
        bot_manager,
        connector_id,
        chat_id,
        settings.oversize_file_message,
    )


async def _prepare_single_telegram_to_chatwoot_attachment(
    attachment: dict[str, Any],
    *,
    bot_manager: TelegramBotManager,
    connector_id: str,
    chat_id: str,
    settings: TelegramSettings,
) -> Base64Attachment | None:
    file_id = attachment.get("file_id")
    if not file_id:
        return None

    if is_over_size_limit(attachment.get("size"), settings.channel_upload_max_mb):
        await _notify_attachment_too_large(bot_manager, connector_id, chat_id, settings)
        return None

    try:
        file_bytes = await download_telegram_attachment(
            bot_manager, connector_id, file_id
        )
    except TelegramBadRequest as exc:
        logger.warning(
            "Skipping unavailable Telegram attachment",
            connector_id=connector_id,
            chat_id=chat_id,
            file_id=file_id,
            error=str(exc),
        )
        return None

    filename, mime_type = _resolve_attachment_file_metadata(attachment)

    if is_over_size_limit(len(file_bytes), settings.chatwoot_upload_max_mb):
        await _notify_attachment_too_large(bot_manager, connector_id, chat_id, settings)
        return None

    return Base64Attachment(
        filename=filename,
        mime_type=mime_type,
        file_type=attachment.get("file_type", "file"),
        data=base64.b64encode(file_bytes).decode("ascii"),
        data_encoding="base64",
    )


async def prepare_telegram_to_chatwoot_attachments(
    message: dict[str, Any],
    *,
    bot_manager: TelegramBotManager,
    settings: TelegramSettings,
) -> dict[str, Any]:
    payload = dict(message.get("payload", {}))
    attachments = payload.get("attachments", [])
    if not attachments:
        return message

    prepared_attachments: list[Base64Attachment] = []

    for attachment in attachments:
        prepared_attachment = await _prepare_single_telegram_to_chatwoot_attachment(
            attachment,
            bot_manager=bot_manager,
            connector_id=str(message["connector_id"]),
            chat_id=str(message["sender"]["external_id"]),
            settings=settings,
        )
        if prepared_attachment is not None:
            prepared_attachments.append(prepared_attachment)

    payload["attachments"] = prepared_attachments
    message["payload"] = payload
    return message
