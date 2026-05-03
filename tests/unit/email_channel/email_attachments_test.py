from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from aioresponses import aioresponses

from email_channel.email_attachments import (
    download_attachment,
    extract_filename_from_url,
    get_extension_from_mime,
    normalize_filename,
    prepare_attachments_data,
    prepare_email_to_chatwoot_attachments,
)
from src.multichannel_gateway.core.attachment_models import Base64Attachment


class TestExtractFilenameFromUrl:
    def test_valid_url_returns_filename(self) -> None:
        assert (
            extract_filename_from_url("https://example.com/document.pdf")
            == "document.pdf"
        )

    def test_empty_url_returns_none(self) -> None:
        assert extract_filename_from_url("") is None

    def test_url_without_filename_returns_none(self) -> None:
        assert extract_filename_from_url("https://example.com/path/") is None

    def test_url_without_extension_returns_none(self) -> None:
        assert extract_filename_from_url("https://example.com/path/document") is None

    def test_url_with_query_params_returns_filename(self) -> None:
        assert (
            extract_filename_from_url("https://example.com/doc.pdf?token=abc")
            == "doc.pdf"
        )


class TestGetExtensionFromMime:
    def test_known_mime_types(self) -> None:
        assert get_extension_from_mime("image/jpeg") == ".jpg"
        assert get_extension_from_mime("image/png") == ".png"
        assert get_extension_from_mime("image/gif") == ".gif"
        assert get_extension_from_mime("image/webp") == ".webp"
        assert get_extension_from_mime("video/mp4") == ".mp4"
        assert get_extension_from_mime("audio/mpeg") == ".mp3"
        assert get_extension_from_mime("audio/ogg") == ".ogg"

    def test_unknown_mime_type_uses_mimetypes(self) -> None:
        assert get_extension_from_mime("application/pdf") != ""

    def test_empty_mime_type_returns_empty(self) -> None:
        assert get_extension_from_mime("") == ""


class TestNormalizeFilename:
    def test_with_data_url(self) -> None:
        attachment: dict[str, Any] = {"data_url": "https://example.com/document.pdf"}
        assert normalize_filename(attachment) == "document.pdf"

    def test_without_data_url_uses_default(self) -> None:
        attachment: dict[str, Any] = {"mime_type": "application/pdf"}
        assert normalize_filename(attachment) == "file.pdf"

    def test_url_without_extension_adds_from_mime(self) -> None:
        attachment: dict[str, Any] = {
            "data_url": "https://example.com/document",
            "mime_type": "image/png",
        }
        assert normalize_filename(attachment) == "file.png"

    def test_no_extension_no_mime_returns_file(self) -> None:
        attachment: dict[str, Any] = {}
        assert normalize_filename(attachment) == "file"


class TestDownloadAttachment:
    @pytest.mark.asyncio
    async def test_success_returns_data(self) -> None:
        url = "https://example.com/file.pdf"
        with aioresponses() as m:
            m.get(url, body=b"content", status=200)
            result = await download_attachment(url)
            assert result == b"content"

    @pytest.mark.asyncio
    async def test_non_200_returns_none(self) -> None:
        url = "https://example.com/file.pdf"
        with aioresponses() as m:
            m.get(url, status=404)
            result = await download_attachment(url)
            assert result is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self) -> None:
        url = "https://example.com/file.pdf"
        with aioresponses() as m:
            m.get(url, exception=Exception("Connection error"))
            result = await download_attachment(url)
            assert result is None


class TestPrepareAttachmentsData:
    @pytest.mark.asyncio
    async def test_with_valid_attachment(self) -> None:
        attachments = [
            {
                "data_url": "https://example.com/file.pdf",
                "mime_type": "application/pdf",
                "size": 100,
            }
        ]

        with patch(
            "email_channel.email_attachments.download_attachment",
            AsyncMock(return_value=b"pdf"),
        ):
            result = await prepare_attachments_data(attachments)

        assert len(result) == 1
        assert result[0][0] == b"pdf"
        assert result[0][1].endswith(".pdf")
        assert result[0][2] == "application/pdf"
        assert result[0][3] == 100

    @pytest.mark.asyncio
    async def test_skips_empty_data_url(self) -> None:
        attachments = [{"mime_type": "application/pdf"}]
        result = await prepare_attachments_data(attachments)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_skips_failed_download(self) -> None:
        attachments = [{"data_url": "https://example.com/file.pdf"}]
        with patch(
            "email_channel.email_attachments.download_attachment",
            AsyncMock(return_value=None),
        ):
            result = await prepare_attachments_data(attachments)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_uses_default_mime_when_missing(self) -> None:
        attachments = [{"data_url": "https://example.com/file.pdf"}]
        with patch(
            "email_channel.email_attachments.download_attachment",
            AsyncMock(return_value=b"data"),
        ):
            result = await prepare_attachments_data(attachments)
        assert result[0][2] == "application/octet-stream"


class TestPrepareEmailToChatwootAttachments:
    def test_with_attachments_converts_to_base64(self) -> None:
        message: dict[str, Any] = {
            "payload": {
                "attachments": [
                    {
                        "data": "dGVzdA==",
                        "filename": "test.txt",
                        "content_type": "text/plain",
                    }
                ]
            }
        }
        result = prepare_email_to_chatwoot_attachments(message)
        atts = result["payload"]["attachments"]
        assert len(atts) == 1
        assert isinstance(atts[0], Base64Attachment)
        assert atts[0].filename == "test.txt"
        assert atts[0].mime_type == "text/plain"

    def test_without_attachments_returns_unchanged(self) -> None:
        message: dict[str, Any] = {"payload": {}}
        result = prepare_email_to_chatwoot_attachments(message)
        assert result == message

    def test_skips_empty_data(self) -> None:
        message: dict[str, Any] = {
            "payload": {
                "attachments": [
                    {"data": "", "filename": "skip.txt"},
                    {"data": "dGVzdA==", "filename": "keep.txt"},
                ]
            }
        }
        result = prepare_email_to_chatwoot_attachments(message)
        assert len(result["payload"]["attachments"]) == 1
        assert result["payload"]["attachments"][0].filename == "keep.txt"

    def test_uses_defaults_when_fields_missing(self) -> None:
        message: dict[str, Any] = {"payload": {"attachments": [{"data": "dGVzdA=="}]}}
        result = prepare_email_to_chatwoot_attachments(message)
        att = result["payload"]["attachments"][0]
        assert att.filename == "attachment"
        assert att.mime_type == "application/octet-stream"
        assert att.file_type == "file"
        assert att.data_encoding == "base64"
