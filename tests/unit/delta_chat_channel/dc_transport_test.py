"""Delta Chat transport tests."""

# mypy: disable-error-code=no-untyped-def

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from channels.delta_chat_channel.dc_models import DeltaChatAccountConfig
from channels.delta_chat_channel.dc_settings import DeltaChatSettings
from channels.delta_chat_channel.dc_transport import DeltaChatTransport
from src import (
    ChannelDeliveryResult,
    ConnectorNotFoundError,
    Envelope,
    FatalError,
    SenderInfo,
    TransientError,
)


class _FakeStreamContent:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def iter_chunked(self, _chunk_size: int):
        for chunk in self._chunks:
            yield chunk


class _FakeResponse:
    def __init__(self, *, status: int = 200, chunks: list[bytes] | None = None) -> None:
        self.status = status
        self.content = _FakeStreamContent(chunks or [b"attachment-bytes"])

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def text(self) -> str:
        return "download-error"


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.requested_urls: list[str] = []

    def get(self, url: str) -> _FakeResponse:
        self.requested_urls.append(url)
        return self._response


class _FakeSessionManager:
    def __init__(self, response: _FakeResponse) -> None:
        self.session = _FakeSession(response)


class TestDeltaChatTransport:
    def test_native_mode_rejects_legacy_bridge_config(
        self, routing, account_config: DeltaChatAccountConfig, identity_store
    ) -> None:
        settings = DeltaChatSettings(
            delta_chat_accounts=[account_config],
            deltachat_accounts_dir="/tmp/deltachat",
            enable_native_deltachat_channel=True,
        )
        client = MagicMock()

        with pytest.raises(ValueError, match="bridge_url is not allowed"):
            DeltaChatTransport(settings, routing, client, identity_store)

    @pytest.mark.asyncio
    async def test_unknown_connector_id_raises_connector_not_found(
        self, routing, account_config: DeltaChatAccountConfig, identity_store
    ) -> None:
        native_account_config = account_config.model_copy(update={"bridge_url": None})
        settings = DeltaChatSettings(
            delta_chat_accounts=[native_account_config],
            deltachat_accounts_dir="/tmp/deltachat",
            enable_native_deltachat_channel=True,
        )
        client = MagicMock()
        cw_session_manager = MagicMock()
        cw_session_manager.session.get = MagicMock()
        transport = DeltaChatTransport(
            settings, routing, client, identity_store, cw_session_manager
        )

        message = Envelope(
            idem_key="key",
            channel="delta_chat",
            from_="chatwoot",
            to="delta_chat",
            connector_id="unknown-connector",
            cw_account_id=native_account_config.cw_account_id,
            cw_inbox_id=native_account_config.cw_inbox_id,
            message_id="msg-1",
            sender=SenderInfo(
                external_id="chatwoot_actor_1", raw_external_id="bot1@example.org"
            ),
            payload={"text": "hello", "attachments": []},
            ts=1.0,
        )

        with pytest.raises(ConnectorNotFoundError):
            await transport.send_to_delta_chat_user(message.model_dump(mode="json"))

        client.get_account.assert_not_called()
        cw_session_manager.session.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_to_user_uses_native_rpc(
        self, routing, account_config: DeltaChatAccountConfig, identity_store
    ) -> None:
        native_account_config = account_config.model_copy(update={"bridge_url": None})
        settings = DeltaChatSettings(
            delta_chat_accounts=[native_account_config],
            deltachat_accounts_dir="/tmp/deltachat",
            enable_native_deltachat_channel=True,
        )
        client = MagicMock()
        account = MagicMock()
        contact = MagicMock()
        chat = MagicMock()
        client.get_account.return_value = account
        account.get_contact_by_addr.return_value = contact
        account.get_chat_by_contact.return_value = chat
        transport = DeltaChatTransport(settings, routing, client, identity_store)
        transport._send_via_bridge = AsyncMock()  # type: ignore[method-assign]

        message = Envelope(
            idem_key="key",
            channel="delta_chat",
            from_="chatwoot",
            to="delta_chat",
            connector_id=account_config.connector_id,
            cw_account_id=native_account_config.cw_account_id,
            cw_inbox_id=native_account_config.cw_inbox_id,
            message_id="msg-1",
            sender=SenderInfo(
                external_id="chatwoot_actor_1", raw_external_id="bot1@example.org"
            ),
            payload={"text": "hello", "attachments": []},
            ts=1.0,
        )

        result = await transport.send_to_delta_chat_user(message.model_dump(mode="json"))

        assert result == ChannelDeliveryResult(ok=True, external_id="bot1@example.org")
        client.get_account.assert_called_once_with(account_config.connector_id)
        account.get_contact_by_addr.assert_called_once_with("bot1@example.org")
        account.create_contact.assert_not_called()
        account.get_chat_by_contact.assert_called_once_with(contact)
        chat.send_message.assert_called_once_with(text="hello")
        transport._send_via_bridge.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_to_user_uses_bridge_when_native_disabled(
        self, routing, account_config: DeltaChatAccountConfig, identity_store
    ) -> None:
        settings = DeltaChatSettings(
            delta_chat_accounts=[account_config],
            deltachat_accounts_dir="/tmp/deltachat",
            enable_native_deltachat_channel=False,
        )
        client = MagicMock()
        transport = DeltaChatTransport(settings, routing, client, identity_store)
        transport._send_via_bridge = AsyncMock(return_value=ChannelDeliveryResult(ok=True, external_id="bot1@example.org"))  # type: ignore[method-assign]

        message = Envelope(
            idem_key="key",
            channel="delta_chat",
            from_="chatwoot",
            to="delta_chat",
            connector_id=account_config.connector_id,
            cw_account_id=account_config.cw_account_id,
            cw_inbox_id=account_config.cw_inbox_id,
            message_id="msg-1",
            sender=SenderInfo(
                external_id="chatwoot_actor_1", raw_external_id="bot1@example.org"
            ),
            payload={"text": "hello", "attachments": []},
            ts=1.0,
        )

        result = await transport.send_to_delta_chat_user(message.model_dump(mode="json"))

        assert result.ok is True
        transport._send_via_bridge.assert_awaited_once()
        client.get_account.assert_not_called()

    @pytest.mark.asyncio
    async def test_outgoing_attachment_downloads_and_cleans_up_temp_file(
        self,
        routing,
        account_config: DeltaChatAccountConfig,
        identity_store,
        tmp_path: Path,
    ) -> None:
        native_account_config = account_config.model_copy(update={"bridge_url": None})
        settings = DeltaChatSettings(
            delta_chat_accounts=[native_account_config],
            deltachat_accounts_dir=str(tmp_path / "deltachat"),
            enable_native_deltachat_channel=True,
        )
        cw_session_manager = _FakeSessionManager(
            _FakeResponse(status=200, chunks=[b"hello", b"world"])
        )
        client = MagicMock()
        account = MagicMock()
        contact = MagicMock()
        chat = MagicMock()
        client.get_account.return_value = account
        account.get_contact_by_addr.return_value = contact
        account.get_chat_by_contact.return_value = chat
        transport = DeltaChatTransport(
            settings, routing, client, identity_store, cw_session_manager
        )

        message = Envelope(
            idem_key="key",
            channel="delta_chat",
            from_="chatwoot",
            to="delta_chat",
            connector_id=account_config.connector_id,
            cw_account_id=native_account_config.cw_account_id,
            cw_inbox_id=native_account_config.cw_inbox_id,
            message_id="msg-1",
            sender=SenderInfo(
                external_id="chatwoot_actor_1", raw_external_id="bot1@example.org"
            ),
            payload={
                "text": "hello",
                "attachments": [
                    {
                        "data_url": "https://chatwoot.example.org/attachment",
                        "filename": "photo.jpg",
                        "mime_type": "image/jpeg",
                        "file_type": "image",
                        "size": 10,
                        "view_type": "image",
                    }
                ],
            },
            ts=1.0,
        )

        result = await transport.send_to_delta_chat_user(message.model_dump(mode="json"))

        assert result.ok is True
        chat.send_message.assert_called_once()
        sent_kwargs = chat.send_message.call_args.kwargs
        temp_path = Path(sent_kwargs["file"])
        assert sent_kwargs["text"] == "hello"
        assert sent_kwargs["filename"] == "photo.jpg"
        assert not temp_path.exists()
        client.get_account.assert_called_once_with(account_config.connector_id)

    @pytest.mark.asyncio
    async def test_outgoing_attachment_rewrites_chatwoot_loopback_url(
        self,
        routing,
        account_config: DeltaChatAccountConfig,
        identity_store,
        tmp_path: Path,
    ) -> None:
        native_account_config = account_config.model_copy(update={"bridge_url": None})
        settings = DeltaChatSettings(
            delta_chat_accounts=[native_account_config],
            deltachat_accounts_dir=str(tmp_path / "deltachat"),
            enable_native_deltachat_channel=True,
            chatwoot_base_url="http://host.docker.internal:3000",
        )
        cw_session_manager = _FakeSessionManager(_FakeResponse())
        client = MagicMock()
        account = MagicMock()
        contact = MagicMock()
        chat = MagicMock()
        client.get_account.return_value = account
        account.get_contact_by_addr.return_value = contact
        account.get_chat_by_contact.return_value = chat
        transport = DeltaChatTransport(
            settings, routing, client, identity_store, cw_session_manager
        )
        message = Envelope(
            idem_key="key",
            channel="delta_chat",
            from_="chatwoot",
            to="delta_chat",
            connector_id=account_config.connector_id,
            cw_account_id=native_account_config.cw_account_id,
            cw_inbox_id=native_account_config.cw_inbox_id,
            message_id="msg-loopback",
            sender=SenderInfo(
                external_id="chatwoot_actor_1", raw_external_id="bot1@example.org"
            ),
            payload={
                "attachments": [
                    {
                        "data_url": "http://localhost:3000/storage/photo.jpg?token=one",
                        "mime_type": "image/jpeg",
                        "file_type": "image",
                        "size": 10,
                    }
                ]
            },
            ts=1.0,
        )

        await transport.send_to_delta_chat_user(message.model_dump(mode="json"))

        assert cw_session_manager.session.requested_urls == [
            "http://host.docker.internal:3000/storage/photo.jpg?token=one"
        ]
        assert chat.send_message.call_args.kwargs["filename"] == "photo.jpg"

    @pytest.mark.asyncio
    async def test_outgoing_attachment_temp_file_is_removed_on_exception(
        self,
        routing,
        account_config: DeltaChatAccountConfig,
        identity_store,
        tmp_path: Path,
    ) -> None:
        native_account_config = account_config.model_copy(update={"bridge_url": None})
        settings = DeltaChatSettings(
            delta_chat_accounts=[native_account_config],
            deltachat_accounts_dir=str(tmp_path / "deltachat"),
            enable_native_deltachat_channel=True,
        )
        cw_session_manager = _FakeSessionManager(_FakeResponse(status=200, chunks=[b"hello"]))
        client = MagicMock()
        account = MagicMock()
        contact = MagicMock()
        chat = MagicMock()
        chat.send_message.side_effect = RuntimeError("send failed")
        client.get_account.return_value = account
        account.get_contact_by_addr.return_value = contact
        account.get_chat_by_contact.return_value = chat
        transport = DeltaChatTransport(
            settings, routing, client, identity_store, cw_session_manager
        )

        message = Envelope(
            idem_key="key",
            channel="delta_chat",
            from_="chatwoot",
            to="delta_chat",
            connector_id=account_config.connector_id,
            cw_account_id=native_account_config.cw_account_id,
            cw_inbox_id=native_account_config.cw_inbox_id,
            message_id="msg-1",
            sender=SenderInfo(
                external_id="chatwoot_actor_1", raw_external_id="bot1@example.org"
            ),
            payload={
                "attachments": [
                    {
                        "data_url": "https://chatwoot.example.org/attachment",
                        "filename": "photo.jpg",
                        "mime_type": "image/jpeg",
                        "file_type": "image",
                        "size": 10,
                        "view_type": "image",
                    }
                ],
            },
            ts=1.0,
        )

        with pytest.raises(TransientError):
            await transport.send_to_delta_chat_user(message.model_dump(mode="json"))

        temp_path = Path(chat.send_message.call_args.kwargs["file"])
        assert not temp_path.exists()

    @pytest.mark.asyncio
    async def test_outgoing_attachment_size_limit_returns_controlled_error(
        self,
        routing,
        account_config: DeltaChatAccountConfig,
        identity_store,
        tmp_path: Path,
    ) -> None:
        native_account_config = account_config.model_copy(update={"bridge_url": None})
        settings = DeltaChatSettings(
            delta_chat_accounts=[native_account_config],
            deltachat_accounts_dir=str(tmp_path / "deltachat"),
            enable_native_deltachat_channel=True,
            chatwoot_upload_max_mb=0,
        )
        cw_session_manager = _FakeSessionManager(_FakeResponse())
        client = MagicMock()
        transport = DeltaChatTransport(
            settings, routing, client, identity_store, cw_session_manager
        )

        message = Envelope(
            idem_key="key",
            channel="delta_chat",
            from_="chatwoot",
            to="delta_chat",
            connector_id=account_config.connector_id,
            cw_account_id=native_account_config.cw_account_id,
            cw_inbox_id=native_account_config.cw_inbox_id,
            message_id="msg-1",
            sender=SenderInfo(
                external_id="chatwoot_actor_1", raw_external_id="bot1@example.org"
            ),
            payload={
                "attachments": [
                    {
                        "data_url": "https://chatwoot.example.org/attachment",
                        "filename": "photo.jpg",
                        "mime_type": "image/jpeg",
                        "file_type": "image",
                        "size": 1,
                        "view_type": "image",
                    }
                ],
            },
            ts=1.0,
        )

        with pytest.raises(FatalError, match="Attachment exceeds configured size limit"):
            await transport.send_to_delta_chat_user(message.model_dump(mode="json"))
