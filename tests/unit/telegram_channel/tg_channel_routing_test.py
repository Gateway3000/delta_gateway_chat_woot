import pytest

from channels.telegram_channel.plugin_settings import BotConfig, TelegramSettings
from channels.telegram_channel.tg_channel import TelegramChannel
from channels.telegram_channel.tg_routing import TelegramRouting


class TestTelegramRouting:
    def test_telegram_channel_exposes_channel_name(
        self,
        telegram_channel: TelegramChannel,
    ) -> None:
        assert telegram_channel.channel == "telegram"

    def test_telegram_routing_resolves_public_route(
        self,
        settings: TelegramSettings,
        routing: TelegramRouting,
        bot_config: BotConfig,
    ) -> None:
        route = routing.get_route_by_connector_id(bot_config.connector_id)

        assert route == {
            "connector_id": bot_config.connector_id,
            "cw_account_id": bot_config.cw_account_id,
            "cw_inbox_id": bot_config.cw_inbox_id,
            "bot_token": bot_config.bot_token,
        }

    def test_telegram_routing_resolves_route_by_chatwoot_inbox(
        self,
        settings: TelegramSettings,
        routing: TelegramRouting,
        bot_config: BotConfig,
    ) -> None:
        route = routing.get_route_by_inbox_id(str(bot_config.cw_inbox_id))
        assert route["connector_id"] == bot_config.connector_id
        assert route["cw_account_id"] == bot_config.cw_account_id

    def test_telegram_routing_rejects_unknown_connector(
        self,
        settings: TelegramSettings,
        routing: TelegramRouting,
    ) -> None:
        with pytest.raises(ValueError, match="Invalid connector_id: missing"):
            routing.get_route_by_connector_id("missing")

    def test_telegram_routing_rejects_unknown_inbox(
        self,
        settings: TelegramSettings,
        routing: TelegramRouting,
    ) -> None:
        with pytest.raises(KeyError):
            routing.get_route_by_inbox_id("missing")
