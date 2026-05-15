import pytest

from channels.telegram_channel.plugin_settings import BotConfig
from channels.telegram_channel.tg_bot_manager import TelegramBotManager


class TestTelegramBotManager:
    def test_get_bot_by_connector_id_returns_bot(
        self,
        bot_config: BotConfig,
    ) -> None:
        manager = TelegramBotManager([bot_config])

        bot = manager.get_bot_by_connector_id(bot_config.connector_id)

        assert bot is not None
        assert bot.token == bot_config.bot_token

    def test_get_bot_by_connector_id_raises_on_unknown(
        self,
        bot_config: BotConfig,
    ) -> None:
        manager = TelegramBotManager([bot_config])

        with pytest.raises(KeyError, match="Invalid connector_id: missing"):
            manager.get_bot_by_connector_id("missing")

    def test_bots_property_returns_mapping(
        self,
        bot_config: BotConfig,
    ) -> None:
        manager = TelegramBotManager([bot_config])

        assert bot_config.connector_id in manager.bots
        assert manager.bots[bot_config.connector_id].token == bot_config.bot_token

    def test_manages_multiple_bots(self) -> None:
        configs = [
            BotConfig(
                connector_id="tg1",
                bot_token="123456:TOKEN1",
                cw_account_id="1",
                cw_inbox_id="10",
            ),
            BotConfig(
                connector_id="tg2",
                bot_token="789012:TOKEN2",
                cw_account_id="2",
                cw_inbox_id="20",
            ),
        ]
        manager = TelegramBotManager(configs)

        assert manager.get_bot_by_connector_id("tg1").token == "123456:TOKEN1"
        assert manager.get_bot_by_connector_id("tg2").token == "789012:TOKEN2"

    @pytest.mark.asyncio
    async def test_close_sessions_closes_all_bot_sessions(
        self,
        bot_config: BotConfig,
    ) -> None:
        manager = TelegramBotManager([bot_config])

        await manager.close_sessions()
