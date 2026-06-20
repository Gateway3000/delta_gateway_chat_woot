from unittest.mock import AsyncMock, MagicMock

import pytest

from channels.delta_chat_channel.dc_models import DeltaChatAccountConfig
from channels.delta_chat_channel.dc_settings import DeltaChatSettings
from channels.delta_chat_channel.dc_transport import DeltaChatTransport
from src import ChannelDeliveryResult, Envelope, SenderInfo


class TestDeltaChatTransport:
    @pytest.mark.asyncio
    async def test_send_to_user_uses_native_rpc(
        self, routing, account_config: DeltaChatAccountConfig, identity_store
    ) -> None:
        settings = DeltaChatSettings(
            delta_chat_accounts=[account_config],
            deltachat_accounts_dir="/tmp/deltachat",
            enable_native_deltachat_channel=True,
        )
        client = MagicMock()
        account = MagicMock()
        contact = MagicMock()
        chat = MagicMock()
        client.get_account.return_value = account
        account.create_contact.return_value = contact
        contact.create_chat.return_value = chat
        transport = DeltaChatTransport(settings, routing, client, identity_store)

        message = Envelope(
            idem_key="key",
            channel="delta_chat",
            from_="chatwoot",
            to="delta_chat",
            connector_id=account_config.connector_id,
            cw_account_id=account_config.cw_account_id,
            cw_inbox_id=account_config.cw_inbox_id,
            message_id="msg-1",
            sender=SenderInfo(external_id="chatwoot_actor_1", raw_external_id="bot1@example.org"),
            payload={"text": "hello", "attachments": []},
            ts=1.0,
        )

        result = await transport.send_to_delta_chat_user(message.model_dump(mode="json"))

        assert result == ChannelDeliveryResult(ok=True, external_id="bot1@example.org")
        client.get_account.assert_called_once_with(account_config.connector_id)
        account.create_contact.assert_called_once()
        contact.create_chat.assert_called_once()
        chat.send_text.assert_called_once_with("hello")

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
            sender=SenderInfo(external_id="chatwoot_actor_1", raw_external_id="bot1@example.org"),
            payload={"text": "hello", "attachments": []},
            ts=1.0,
        )

        result = await transport.send_to_delta_chat_user(message.model_dump(mode="json"))

        assert result.ok is True
        transport._send_via_bridge.assert_awaited_once()

