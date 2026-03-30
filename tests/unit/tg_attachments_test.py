from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import GetFile

from telegram.plugin_settings import TelegramSettings
from telegram.tg_attachments import (
    extract_telegram_attachments,
    prepare_inbound_attachments,
)


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


class TestPrepareInboundAttachments:
    @staticmethod
    def _build_settings(
        *,
        channel_upload_max_mb: int = 20,
        chatwoot_upload_max_mb: int = 40,
        oversize_file_message: str = "too large",
    ) -> TelegramSettings:
        return TelegramSettings(
            channel_upload_max_mb=channel_upload_max_mb,
            chatwoot_upload_max_mb=chatwoot_upload_max_mb,
            oversize_file_message=oversize_file_message,
        )

    @pytest.mark.asyncio
    async def test_validate_and_download_returns_original_message_when_no_attachments(
        self,
    ) -> None:
        settings = self._build_settings()
        bot_manager = Mock()
        message = {"payload": {"text": "hello", "attachments": []}}

        prepared = await prepare_inbound_attachments(
            message,
            bot_manager=bot_manager,
            settings=settings,
        )

        assert prepared is message

    @pytest.mark.asyncio
    async def test_validate_and_download_downloads_attachment_and_keeps_it_for_later_upload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "telegram.tg_attachments.tempfile.gettempdir", lambda: str(tmp_path)
        )
        temp_file_path = tmp_path / "channel-gateway" / "report.pdf"

        bot = Mock()
        bot.get_file = AsyncMock(return_value=Mock(file_path="docs/report.pdf"))
        bot.download_file = AsyncMock(
            side_effect=lambda _file_path, destination: Path(destination).write_bytes(
                b"pdf-bytes"
            )
        )
        bot.send_message = AsyncMock()
        bot_manager = Mock()
        bot_manager.get_bot_by_connector_id.return_value = bot
        settings = self._build_settings()
        message = {
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

        prepared = await prepare_inbound_attachments(
            message,
            bot_manager=bot_manager,
            settings=settings,
        )

        attachments = prepared["payload"]["attachments"]
        assert len(attachments) == 1
        assert attachments[0].kind == "local_file"
        assert attachments[0].filename == "report.pdf"
        assert attachments[0].mime_type == "application/pdf"
        assert attachments[0].file_type == "file"
        assert attachments[0].temp_file_path == temp_file_path
        bot_manager.get_bot_by_connector_id.assert_called_with("tg1")
        bot.get_file.assert_awaited_once_with("file-1")
        bot.download_file.assert_awaited_once_with(
            "docs/report.pdf", destination=str(temp_file_path)
        )
        bot.send_message.assert_not_awaited()
        assert temp_file_path.exists()

    @pytest.mark.asyncio
    async def test_validate_and_download_notifies_user_and_skips_oversize_attachment(
        self,
    ) -> None:
        bot = Mock()
        bot.get_file = AsyncMock()
        bot.download_file = AsyncMock()
        bot.send_message = AsyncMock()
        bot_manager = Mock()
        bot_manager.get_bot_by_connector_id.return_value = bot
        settings = self._build_settings(
            channel_upload_max_mb=1,
        )
        message = {
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

        prepared = await prepare_inbound_attachments(
            message,
            bot_manager=bot_manager,
            settings=settings,
        )

        assert prepared["payload"]["attachments"] == []
        bot.send_message.assert_awaited_once_with(
            chat_id="123",
            text="too large",
        )
        bot.get_file.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_validate_and_download_skips_unavailable_telegram_attachment(
        self,
    ) -> None:
        bot = Mock()
        bot.get_file = AsyncMock(
            side_effect=TelegramBadRequest(
                method=GetFile(file_id="file-1"),
                message=(
                    "Telegram server says - Bad Request: wrong file_id or the file "
                    "is temporarily unavailable"
                ),
            )
        )
        bot.download_file = AsyncMock()
        bot.send_message = AsyncMock()
        bot_manager = Mock()
        bot_manager.get_bot_by_connector_id.return_value = bot
        settings = self._build_settings()
        message = {
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

        prepared = await prepare_inbound_attachments(
            message,
            bot_manager=bot_manager,
            settings=settings,
        )

        assert prepared["payload"]["attachments"] == []
        bot.get_file.assert_awaited_once_with("file-1")
        bot.download_file.assert_not_awaited()
        bot.send_message.assert_not_awaited()
