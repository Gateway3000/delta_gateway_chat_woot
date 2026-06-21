"""Delta Chat attachment helper tests."""

# mypy: disable-error-code=no-untyped-def

from pathlib import Path

from channels.delta_chat_channel.dc_attachments import (
    extract_delta_chat_attachments,
    prepare_delta_chat_to_chatwoot_attachments,
)


def test_incoming_image_creates_gateway_attachment(tmp_path: Path) -> None:
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(b"image-bytes")

    attachments = extract_delta_chat_attachments(
        {
            "file": str(image_path),
            "file_name": "photo.jpg",
            "mime_type": "image/jpeg",
            "view_type": "image",
            "message_id": "msg-1",
            "chat_id": 7,
        }
    )

    assert attachments == [
        {
            "source": "deltachat",
            "file_type": "image",
            "file_id": "msg-1",
            "data_url": None,
            "path": str(image_path),
            "file_path": str(image_path),
            "filename": "photo.jpg",
            "mime_type": "image/jpeg",
            "view_type": "image",
            "size": None,
        }
    ]


def test_incoming_document_keeps_name_and_mime(tmp_path: Path) -> None:
    doc_path = tmp_path / "report.pdf"
    doc_path.write_bytes(b"pdf-bytes")

    attachments = extract_delta_chat_attachments(
        {
            "file": str(doc_path),
            "filename": "report.pdf",
            "mime_type": "application/pdf",
            "message_id": "msg-2",
        }
    )

    assert attachments[0]["filename"] == "report.pdf"
    assert attachments[0]["mime_type"] == "application/pdf"
    assert attachments[0]["file_type"] == "file"


def test_incoming_voice_normalizes_to_audio(tmp_path: Path) -> None:
    voice_path = tmp_path / "voice.ogg"
    voice_path.write_bytes(b"voice-bytes")

    attachments = extract_delta_chat_attachments(
        {
            "file": str(voice_path),
            "mime_type": "audio/ogg",
            "view_type": "voice",
            "message_id": "msg-3",
        }
    )

    assert attachments[0]["file_type"] == "audio"
    assert attachments[0]["view_type"] == "voice"


def test_incoming_voice_falls_back_to_ogg_metadata(tmp_path: Path) -> None:
    voice_path = tmp_path / "voice-note"
    voice_path.write_bytes(b"voice-bytes")

    attachments = extract_delta_chat_attachments(
        {
            "file": str(voice_path),
            "view_type": "voice",
            "message_id": "msg-4",
        }
    )

    assert attachments[0]["filename"] == "voice.ogg"
    assert attachments[0]["mime_type"] == "audio/ogg"
    assert attachments[0]["file_type"] == "audio"


def test_prepare_delta_chat_to_chatwoot_attachments_encodes_file(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "clip.mp3"
    file_path.write_bytes(b"binary-audio")

    prepared = prepare_delta_chat_to_chatwoot_attachments(
        [
            {
                "path": str(file_path),
                "filename": "clip.mp3",
                "mime_type": "audio/mpeg",
                "file_type": "audio",
                "size": file_path.stat().st_size,
            }
        ],
        max_mb=1,
    )

    assert len(prepared) == 1
    assert prepared[0].filename == "clip.mp3"
    assert prepared[0].mime_type == "audio/mpeg"
    assert prepared[0].file_type == "audio"
    assert prepared[0].data_encoding == "base64"
