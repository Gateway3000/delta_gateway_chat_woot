import base64
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import GetFile

from channels.telegram_channel.plugin_settings import TelegramSettings
from channels.telegram_channel.tg_attachments import (
    _safe_int,
    is_over_size_limit,
    extract_telegram_attachments,
    download_telegram_attachment,
    notify_telegram_user,
    _resolve_attachment_file_metadata,
    _prepare_single_telegram_to_chatwoot_attachment,
    prepare_telegram_to_chatwoot_attachments,
)


class TestSafeInt:
    def test_with_valid_int(self) -> None:
        assert _safe_int(42) == 42

    def test_with_valid_str_number(self) -> None:
        assert _safe_int("42") == 42

    def test_with_none(self) -> None:
        assert _safe_int(None) is None

    def test_with_invalid_str(self) -> None:
        assert _safe_int("bad") is None


class TestIsOverSizeLimit:
    def test_exceeds_limit(self) -> None:
        assert is_over_size_limit(2 * 1024 * 1024, 1) is True

    def test_within_limit(self) -> None:
        assert is_over_size_limit(1, 1) is False

    def test_none_size_returns_false(self) -> None:
        assert is_over_size_limit(None, 100) is False


class TestTelegramAttachmentExtraction:
    def test_extract_normalizes_supported_telegram_attachments(self) -> None:
        raw_data = {
            "message": {
                "photo": [
                    {"file_id": "photo-small", "file_size": "100"},
                    {"file_id": "photo-large", "file_size": "200"},
                ],
                "video": {
                    "file_id": "video-1",
                    "file_name": "demo.mp4",
                    "mime_type": "video/mp4",
                    "file_size": "300",
                },
                "document": {
                    "file_id": "doc-1",
                    "file_name": "report.pdf",
                    "mime_type": "application/pdf",
                    "file_size": "bad-size",
                },
                "voice": {
                    "file_id": "voice-1",
                    "mime_type": "audio/ogg",
                    "file_size": 400,
                },
            }
        }

        attachments = extract_telegram_attachments(raw_data)

        assert attachments == [
            {
                "source": "telegram",
                "file_type": "image",
                "file_id": "photo-large",
                "data_url": None,
                "filename": "photo.jpg",
                "mime_type": "image/jpeg",
                "size": 200,
            },
            {
                "source": "telegram",
                "file_type": "video",
                "file_id": "video-1",
                "data_url": None,
                "filename": "demo.mp4",
                "mime_type": "video/mp4",
                "size": 300,
            },
            {
                "source": "telegram",
                "file_type": "audio",
                "file_id": "voice-1",
                "data_url": None,
                "filename": "voice.ogg",
                "mime_type": "audio/ogg",
                "size": 400,
            },
            {
                "source": "telegram",
                "file_type": "file",
                "file_id": "doc-1",
                "data_url": None,
                "filename": "report.pdf",
                "mime_type": "application/pdf",
                "size": None,
            },
        ]

    def test_extract_returns_empty_list_when_message_has_no_attachments(self) -> None:
        assert extract_telegram_attachments({"message": {"text": "hello"}}) == []

    def test_extract_video_note_attachment(self) -> None:
        raw_data = {
            "message": {
                "video_note": {"file_id": "vn-1", "file_size": 500},
            }
        }

        attachments = extract_telegram_attachments(raw_data)

        assert attachments == [
            {
                "source": "telegram",
                "file_type": "video",
                "file_id": "vn-1",
                "data_url": None,
                "filename": "video_note.mp4",
                "mime_type": "video/mp4",
                "size": 500,
            }
        ]

    def test_extract_audio_attachment(self) -> None:
        raw_data = {
            "message": {
                "audio": {
                    "file_id": "a-1",
                    "file_name": "song.mp3",
                    "mime_type": "audio/mpeg",
                    "file_size": 1000,
                },
            }
        }

        attachments = extract_telegram_attachments(raw_data)

        assert attachments == [
            {
                "source": "telegram",
                "file_type": "audio",
                "file_id": "a-1",
                "data_url": None,
                "filename": "song.mp3",
                "mime_type": "audio/mpeg",
                "size": 1000,
            }
        ]

    def test_extract_sticker_attachment(self) -> None:
        raw_data = {
            "message": {
                "sticker": {"file_id": "s-1", "file_size": 200},
            }
        }

        attachments = extract_telegram_attachments(raw_data)

        assert attachments == [
            {
                "source": "telegram",
                "file_type": "image",
                "file_id": "s-1",
                "data_url": None,
                "filename": "sticker.webp",
                "mime_type": "image/webp",
                "size": 200,
            }
        ]

    def test_extract_animation_attachment(self) -> None:
        raw_data = {
            "message": {
                "animation": {
                    "file_id": "g-1",
                    "file_name": "anim.gif",
                    "mime_type": "image/gif",
                    "file_size": 300,
                },
            }
        }

        attachments = extract_telegram_attachments(raw_data)

        assert attachments == [
            {
                "source": "telegram",
                "file_type": "image",
                "file_id": "g-1",
                "data_url": None,
                "filename": "anim.gif",
                "mime_type": "image/gif",
                "size": 300,
            }
        ]


class TestResolveAttachmentFileMetadata:
    def test_returns_filename_and_mime_type(self) -> None:
        attachment: dict[str, Any] = {
            "filename": "doc.pdf",
            "mime_type": "application/pdf",
        }
        filename, mime_type = _resolve_attachment_file_metadata(attachment)
        assert filename == "doc.pdf"
        assert mime_type == "application/pdf"

    def test_missing_fields_uses_defaults(self) -> None:
        attachment: dict[str, Any] = {}
        filename, mime_type = _resolve_attachment_file_metadata(attachment)
        assert filename == "unknown"
        assert mime_type == "application/octet-stream"


class TestDownloadTelegramAttachment:
    @pytest.mark.asyncio
    async def test_success_returns_bytes(
        self, tg_bot: Mock, bot_manager: MagicMock
    ) -> None:
        tg_bot.get_file = AsyncMock(return_value=Mock(file_path="docs/report.pdf"))
        tg_bot.download_file = AsyncMock(
            side_effect=lambda _path, destination: destination.write(b"pdf-bytes")
        )

        result = await download_telegram_attachment(bot_manager, "tg1", "file-1")

        assert result == b"pdf-bytes"
        tg_bot.get_file.assert_awaited_once_with("file-1")
        tg_bot.download_file.assert_awaited_once()
        assert tg_bot.download_file.call_args[0][0] == "docs/report.pdf"

    @pytest.mark.asyncio
    async def test_empty_file_path_raises_value_error(
        self, tg_bot: Mock, bot_manager: MagicMock
    ) -> None:
        tg_bot.get_file = AsyncMock(return_value=Mock(file_path=None))

        with pytest.raises(
            ValueError, match="Telegram file_path is empty for file_id=file-1"
        ):
            await download_telegram_attachment(bot_manager, "tg1", "file-1")


class TestNotifyTelegramUser:
    @pytest.mark.asyncio
    async def test_sends_message(self, tg_bot: Mock, bot_manager: MagicMock) -> None:
        await notify_telegram_user(bot_manager, "tg1", 123, "Hello")

        tg_bot.send_message.assert_awaited_once_with(chat_id=123, text="Hello")


class TestPrepareSingleTelegramToChatwootAttachment:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_file_id(
        self,
        bot_manager: MagicMock,
        default_settings: TelegramSettings,
    ) -> None:
        attachment: dict[str, Any] = {}

        result = await _prepare_single_telegram_to_chatwoot_attachment(
            attachment,
            bot_manager=bot_manager,
            connector_id="tg1",
            chat_id="123",
            settings=default_settings,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_notifies_and_skips_when_exceeds_chatwoot_upload_limit(
        self,
        tg_bot: Mock,
        bot_manager: MagicMock,
    ) -> None:
        tg_bot.get_file = AsyncMock(return_value=Mock(file_path="medium.mov"))
        download_size = 2 * 1024 * 1024
        tg_bot.download_file = AsyncMock(
            side_effect=lambda _path, destination: destination.write(
                b"x" * download_size
            )
        )
        small_limit_settings = TelegramSettings(
            channel_upload_max_mb=20,
            chatwoot_upload_max_mb=1,
            oversize_file_message="too large",
            enable_channel_delivery_confirmation=False,
        )
        attachment: dict[str, Any] = {
            "file_id": "file-1",
            "filename": "medium.mov",
            "mime_type": "video/quicktime",
            "file_type": "video",
            "size": 100,
        }

        result = await _prepare_single_telegram_to_chatwoot_attachment(
            attachment,
            bot_manager=bot_manager,
            connector_id="tg1",
            chat_id="123",
            settings=small_limit_settings,
        )

        assert result is None
        tg_bot.send_message.assert_awaited_once_with(chat_id="123", text="too large")


class TestPrepareTelegramToChatwootAttachments:
    @pytest.mark.asyncio
    async def test_returns_original_message_when_no_attachments(
        self,
        bot_manager: MagicMock,
        default_settings: TelegramSettings,
    ) -> None:
        message: dict[str, Any] = {"payload": {"text": "hello", "attachments": []}}

        prepared = await prepare_telegram_to_chatwoot_attachments(
            message,
            bot_manager=bot_manager,
            settings=default_settings,
        )

        assert prepared is message

    @pytest.mark.asyncio
    async def test_downloads_attachment_and_keeps_it_for_later_upload(
        self,
        tg_bot: Mock,
        bot_manager: MagicMock,
        default_settings: TelegramSettings,
    ) -> None:
        tg_bot.get_file = AsyncMock(return_value=Mock(file_path="docs/report.pdf"))
        tg_bot.download_file = AsyncMock(
            side_effect=lambda _file_path, destination: destination.write(b"pdf-bytes")
        )
        message: dict[str, Any] = {
            "connector_id": "tg1",
            "sender": {"external_id": "123"},
            "payload": {
                "text": "hello",
                "attachments": [
                    {
                        "file_id": "file-1",
                        "filename": "report.pdf",
                        "mime_type": "application/pdf",
                        "size": 100,
                    }
                ],
            },
        }

        prepared = await prepare_telegram_to_chatwoot_attachments(
            message,
            bot_manager=bot_manager,
            settings=default_settings,
        )

        attachments = prepared["payload"]["attachments"]
        assert len(attachments) == 1
        assert attachments[0].kind == "base64"
        assert attachments[0].filename == "report.pdf"
        assert attachments[0].mime_type == "application/pdf"
        assert attachments[0].file_type == "file"
        assert attachments[0].data_encoding == "base64"
        assert attachments[0].data == base64.b64encode(b"pdf-bytes").decode("ascii")
        bot_manager.get_bot_by_connector_id.assert_called_with("tg1")
        tg_bot.get_file.assert_awaited_once_with("file-1")
        tg_bot.download_file.assert_awaited_once()
        assert tg_bot.download_file.call_args[0][0] == "docs/report.pdf"
        tg_bot.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_notifies_user_and_skips_oversize_attachment(
        self,
        tg_bot: Mock,
        bot_manager: MagicMock,
    ) -> None:
        settings = TelegramSettings(
            channel_upload_max_mb=1,
            oversize_file_message="too large",
        )
        message: dict[str, Any] = {
            "connector_id": "tg1",
            "sender": {"external_id": "123"},
            "payload": {
                "attachments": [
                    {
                        "file_id": "file-1",
                        "filename": "video.mp4",
                        "mime_type": "video/mp4",
                        "size": 2 * 1024 * 1024,
                    }
                ]
            },
        }

        prepared = await prepare_telegram_to_chatwoot_attachments(
            message,
            bot_manager=bot_manager,
            settings=settings,
        )

        assert prepared["payload"]["attachments"] == []
        tg_bot.send_message.assert_awaited_once_with(chat_id="123", text="too large")
        tg_bot.get_file.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_unavailable_telegram_attachment(
        self,
        tg_bot: Mock,
        bot_manager: MagicMock,
        default_settings: TelegramSettings,
    ) -> None:
        tg_bot.get_file = AsyncMock(
            side_effect=TelegramBadRequest(
                method=GetFile(file_id="file-1"),
                message=(
                    "Telegram server says - Bad Request: wrong file_id or the file "
                    "is temporarily unavailable"
                ),
            )
        )
        message: dict[str, Any] = {
            "connector_id": "tg1",
            "sender": {"external_id": "123"},
            "payload": {
                "text": "hello",
                "attachments": [
                    {
                        "file_id": "file-1",
                        "filename": "report.pdf",
                        "mime_type": "application/pdf",
                        "size": 100,
                    }
                ],
            },
        }

        prepared = await prepare_telegram_to_chatwoot_attachments(
            message,
            bot_manager=bot_manager,
            settings=default_settings,
        )

        assert prepared["payload"]["attachments"] == []
        tg_bot.get_file.assert_awaited_once_with("file-1")
        tg_bot.download_file.assert_not_awaited()
        tg_bot.send_message.assert_not_awaited()
