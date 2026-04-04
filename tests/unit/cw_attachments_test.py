from src.multichannel_gateway.app.chatwoot_attachments import (
    extract_chatwoot_attachments,
)


class TestChatwootAttachmentExtraction:
    def test_extract_normalizes_chatwoot_attachments(self) -> None:
        raw_data = {
            "attachments": [
                {
                    "file_type": "image",
                    "data_url": "https://cdn.example/image.jpg",
                    "file_name": "image.jpg",
                    "content_type": "image/jpeg",
                    "file_size": "123",
                },
                {
                    "file_type": "unsupported",
                    "data_url": "https://cdn.example/file.bin",
                    "filename": "file.bin",
                    "content_type": "application/octet-stream",
                    "file_size": "bad-size",
                },
            ]
        }

        attachments = extract_chatwoot_attachments(raw_data)

        assert attachments == [
            {
                "source": "chatwoot",
                "file_type": "image",
                "file_id": None,
                "data_url": "https://cdn.example/image.jpg",
                "filename": "image.jpg",
                "mime_type": "image/jpeg",
                "size": 123,
            },
            {
                "source": "chatwoot",
                "file_type": "file",
                "file_id": None,
                "data_url": "https://cdn.example/file.bin",
                "filename": "file.bin",
                "mime_type": "application/octet-stream",
                "size": None,
            },
        ]

    def test_extract_returns_empty_list_when_attachments_are_missing(self) -> None:
        assert extract_chatwoot_attachments({"content": "hello"}) == []
