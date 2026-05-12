from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from email_channel import (
    EmailChannel,
    EmailImapClient,
    EmailImapWatcher,
    EmailMessageProcessor,
    EmailRouting,
    EmailTransport,
)
from email_channel.plugin_settings import MailboxConfig
from src import ChannelDeliveryResult, Envelope, SenderInfo


class TestEmailChannel:
    def test_get_route_by_connector_id(
        self,
        channel: EmailChannel,
        routing: EmailRouting,
        mailbox: MailboxConfig,
    ) -> None:
        result = channel.get_route_by_connector_id(mailbox.connector_id)
        expected = routing.get_route_by_connector_id(mailbox.connector_id)

        assert result == expected
        assert "imap_password" not in result
        assert "smtp_password" not in result

    @pytest.mark.asyncio
    async def test_send_to_user(
        self,
        channel: EmailChannel,
        transport: EmailTransport,
        mailbox: MailboxConfig,
    ) -> None:
        message = {
            "channel": "email",
            "connector_id": mailbox.connector_id,
            "sender": {"external_id": "user@example.com"},
            "payload": {"text": "Hello"},
        }

        with patch.object(
            transport, "send_to_email_user", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = ChannelDeliveryResult(ok=True)
            result = await channel.send_to_user(message)

            mock_send.assert_awaited_once_with(message)
            assert result.ok is True

    @pytest.mark.asyncio
    async def test_publish_channel_message(
        self,
        channel: EmailChannel,
        processor: EmailMessageProcessor,
        mailbox: MailboxConfig,
    ) -> None:
        idempotency_key = "key-1"
        envelope = Envelope(
            idem_key=idempotency_key,
            channel="email",
            from_="email",
            to="chatwoot",
            connector_id=mailbox.connector_id,
            cw_account_id=mailbox.cw_account_id,
            cw_inbox_id=mailbox.cw_inbox_id,
            message_id="<x@example.com>",
            sender=SenderInfo(external_id=mailbox.imap_username),
            payload={"text": "hello"},
            ts=1.0,
        )
        raw_data: dict[str, Any] = {}

        with patch.object(
            processor, "publish_channel_message", new_callable=AsyncMock
        ) as mock_pub:
            await channel.publish_channel_message(idempotency_key, envelope, raw_data)
            mock_pub.assert_awaited_once_with(idempotency_key, envelope)

    @pytest.mark.asyncio
    async def test_publish_chatwoot_message(
        self,
        channel: EmailChannel,
        processor: EmailMessageProcessor,
        mailbox: MailboxConfig,
    ) -> None:
        raw_data = {
            "inbox": {"id": int(mailbox.cw_inbox_id)},
            "conversation": {"meta": {"sender": {"identifier": mailbox.imap_username}}},
            "content": "reply",
        }
        cw_account_id = mailbox.cw_account_id

        with patch.object(
            processor, "publish_chatwoot_message", new_callable=AsyncMock
        ) as mock_pub:
            await channel.publish_chatwoot_message(raw_data, cw_account_id)
            mock_pub.assert_awaited_once_with(raw_data, cw_account_id, channel.channel)

    @pytest.mark.asyncio
    async def test_on_startup(
        self, channel: EmailChannel, watcher: EmailImapWatcher
    ) -> None:
        await channel.on_startup()
        assert watcher._task is not None
        await channel.on_shutdown()

    @pytest.mark.asyncio
    async def test_on_shutdown(
        self, channel: EmailChannel, watcher: EmailImapWatcher
    ) -> None:
        await channel.on_startup()
        assert watcher._task is not None

        await channel.on_shutdown()
        assert watcher._task is None

    @pytest.mark.asyncio
    async def test_build_channel_message(
        self, channel: EmailChannel, processor: EmailMessageProcessor
    ) -> None:
        raw_data = {"test": "data"}
        expected: tuple[str, Envelope] = ("key", MagicMock(spec=Envelope))

        with patch.object(
            processor, "build_channel_message", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = expected
            result = await channel.build_channel_message(raw_data)
            mock_build.assert_awaited_once_with(raw_data)
            assert result == expected

    @pytest.mark.asyncio
    async def test_on_prefork(
        self, channel: EmailChannel, imap_client: EmailImapClient
    ) -> None:
        with patch.object(imap_client, "validate_connections") as mock_validate:
            await channel.on_prefork()
            mock_validate.assert_called_once()
