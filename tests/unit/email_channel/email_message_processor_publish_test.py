from unittest.mock import patch

import pytest

from email_channel import (
    EmailImapClient,
    EmailMessageProcessor,
    EmailRouting,
)
from email_channel.plugin_settings import MailboxConfig
from src import (
    Envelope,
    IdempotencyKeyAlreadyProcessedError,
    SenderInfo,
)


def _envelope(mailbox: MailboxConfig) -> Envelope:
    return Envelope(
        idem_key="key-1",
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


class TestEmailMessageProcessor:
    @pytest.mark.asyncio
    async def test_publish_channel_message_sends_and_marks_processed(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        processor: EmailMessageProcessor,
    ) -> None:
        processor._mq.is_already_processed.return_value = False  # type: ignore[attr-defined]

        await processor.publish_channel_message("key-1", _envelope(mailbox))

        processor._mq.is_already_processed.assert_awaited_once_with("key-1")  # type: ignore[attr-defined]
        processor._mq.send.assert_awaited_once()  # type: ignore[attr-defined]
        processor._mq.mark_as_processed.assert_awaited_once_with("key-1")  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_publish_channel_message_raises_on_duplicate_idempotency(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        processor: EmailMessageProcessor,
    ) -> None:
        processor._mq.is_already_processed.return_value = True  # type: ignore[attr-defined]

        with pytest.raises(IdempotencyKeyAlreadyProcessedError):
            await processor.publish_channel_message("key-1", _envelope(mailbox))

        processor._mq.send.assert_not_awaited()  # type: ignore[attr-defined]
        processor._mq.mark_as_processed.assert_not_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_publish_chatwoot_message_sends_to_outgoing_queue(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        processor: EmailMessageProcessor,
    ) -> None:
        processor._mq.is_already_processed.return_value = False  # type: ignore[attr-defined]

        raw_data = {
            "inbox": {"id": int(mailbox.cw_inbox_id)},
            "conversation": {
                "meta": {"sender": {"identifier": mailbox.imap_username}},
                "messages": [{"id": 321}],
            },
            "content": "reply body",
            "attachments": [],
        }

        await processor.publish_chatwoot_message(
            raw_data, mailbox.cw_account_id, "email"
        )

        processor._mq.is_already_processed.assert_awaited_once()  # type: ignore[attr-defined]
        processor._mq.send.assert_awaited_once()  # type: ignore[attr-defined]
        queue_name = processor._mq.send.await_args.args[0]  # type: ignore[attr-defined]
        assert queue_name == "from_cw"
        processor._mq.mark_as_processed.assert_awaited_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_publish_chatwoot_message_raises_on_duplicate_idempotency(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        processor: EmailMessageProcessor,
    ) -> None:
        processor._mq.is_already_processed.return_value = True  # type: ignore[attr-defined]

        raw_data = {
            "inbox": {"id": int(mailbox.cw_inbox_id)},
            "conversation": {
                "meta": {"sender": {"identifier": mailbox.imap_username}},
                "messages": [{"id": 321}],
            },
            "content": "reply body",
        }

        with pytest.raises(IdempotencyKeyAlreadyProcessedError):
            await processor.publish_chatwoot_message(
                raw_data, mailbox.cw_account_id, "email"
            )

        processor._mq.send.assert_not_awaited()  # type: ignore[attr-defined]
        processor._mq.mark_as_processed.assert_not_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_poll_once_calls_handle_channel_payload(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        imap_client: EmailImapClient,
        processor: EmailMessageProcessor,
    ) -> None:
        """Test that poll_once calls handle_channel_payload for each payload."""
        processor._imap_client.fetch_inbound_payloads.return_value = [  # type: ignore[attr-defined]
            {
                "channel": "email",
                "connector_id": mailbox.connector_id,
                "uid": 42,
                "uidvalidity": 777,
                "message_id": "<abc@example.com>",
                "subject": "Hello",
                "text": "World",
                "sender": {"email": mailbox.imap_username},
            },
        ]

        with patch(
            "email_channel.email_message_processor.handle_channel_payload"
        ) as mock_handle:
            await processor.poll_once()
            mock_handle.assert_awaited_once_with(
                "email",
                mailbox.connector_id,
                processor._imap_client.fetch_inbound_payloads.return_value[0],  # type: ignore[attr-defined]
            )

    @pytest.mark.asyncio
    async def test_poll_once_processes_provider_batch(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        imap_client: EmailImapClient,
        processor: EmailMessageProcessor,
    ) -> None:
        payloads = [
            {
                "channel": "email",
                "connector_id": mailbox.connector_id,
                "uid": 42,
                "uidvalidity": 777,
                "message_id": "<abc@example.com>",
                "subject": "A",
                "text": "B",
                "sender": {"email": "a@example.com"},
            },
            {
                "channel": "email",
                "connector_id": mailbox.connector_id,
                "uid": 43,
                "uidvalidity": 777,
                "message_id": "<def@example.com>",
                "subject": "C",
                "text": "D",
                "sender": {"email": "b@example.com"},
            },
        ]
        processor._imap_client.fetch_inbound_payloads.return_value = payloads  # type: ignore[attr-defined]

        with patch(
            "email_channel.email_message_processor.handle_channel_payload"
        ) as mock_handle:
            await processor.poll_once()
            assert mock_handle.await_count == 2
            mock_handle.assert_any_await("email", mailbox.connector_id, payloads[0])
            mock_handle.assert_any_await("email", mailbox.connector_id, payloads[1])

    @pytest.mark.asyncio
    async def test_poll_once_uses_email_imap_client_provider(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        imap_client: EmailImapClient,
        processor: EmailMessageProcessor,
    ) -> None:
        processor._mq.is_already_processed.return_value = False  # type: ignore[attr-defined]
        processor._imap_client.fetch_inbound_payloads.return_value = []  # type: ignore[attr-defined]

        await processor.poll_once()

        processor._imap_client.fetch_inbound_payloads.assert_awaited_once()  # type: ignore[attr-defined]
        processor._mq.send.assert_not_awaited()  # type: ignore[attr-defined]
        processor._mq.mark_as_processed.assert_not_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_publish_channel_message_logs_error_on_queue_failure(
        self, processor: EmailMessageProcessor, mailbox: MailboxConfig
    ) -> None:
        """Test that _process_queue logs error when MQ send fails (covers lines 60-61)."""
        processor._mq.is_already_processed.return_value = False  # type: ignore[attr-defined]
        processor._mq.send.side_effect = Exception("test queue error")  # type: ignore[attr-defined]
        envelope = _envelope(mailbox)
        with patch("email_channel.email_message_processor.logger") as mock_logger:
            await processor.publish_channel_message("key-1", envelope)
            mock_logger.error.assert_called_once_with(
                "Exception occurred: test queue error"
            )

    @pytest.mark.asyncio
    async def test_poll_once_logs_error_on_handle_payload_failure(
        self,
        routing: EmailRouting,
        mailbox: MailboxConfig,
        processor: EmailMessageProcessor,
    ) -> None:
        """Test that poll_once logs error when handle_channel_payload fails (covers lines 81-82)."""
        payload = {
            "channel": "email",
            "connector_id": mailbox.connector_id,
            "uid": 42,
            "uidvalidity": 777,
            "message_id": "<abc@example.com>",
            "subject": "Hello",
            "text": "World",
            "sender": {"email": mailbox.imap_username},
        }
        processor._imap_client.fetch_inbound_payloads.return_value = [payload]  # type: ignore[attr-defined]
        with (
            patch(
                "email_channel.email_message_processor.handle_channel_payload",
                side_effect=Exception("test handle error"),
            ),
            patch("email_channel.email_message_processor.logger") as mock_logger,
        ):
            await processor.poll_once()
            mock_logger.error.assert_called_once_with(
                "Failed to process IMAP payload",
                error="test handle error",
                payload=payload,
            )
