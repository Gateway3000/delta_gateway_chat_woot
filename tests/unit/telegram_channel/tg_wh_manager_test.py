from unittest.mock import AsyncMock, patch

import pytest

from channels.telegram_channel.plugin_settings import BotConfig
from channels.telegram_channel.tg_bot_manager import TelegramBotManager
from channels.telegram_channel.tg_wh_manager import TelegramWebhookManager


class TestTelegramWebhookManager:
    def test_init_stores_values(
        self,
        bot_config: BotConfig,
    ) -> None:
        bot_manager = TelegramBotManager([bot_config])
        wh_manager = TelegramWebhookManager(
            "https://example.com",
            "mysecret",
            bot_manager,
        )

        assert wh_manager._wh_domain == "https://example.com"
        assert wh_manager._secret_token == "mysecret"
        assert wh_manager._bots is bot_manager

    @pytest.mark.asyncio
    async def test_set_wh_raises_on_missing_domain(
        self,
        bot_config: BotConfig,
    ) -> None:
        bot_manager = TelegramBotManager([bot_config])
        wh_manager = TelegramWebhookManager(None, "mysecret", bot_manager)

        with pytest.raises(ValueError, match="WH_DOMAIN must be set"):
            await wh_manager.set_wh()

    @pytest.mark.asyncio
    async def test_set_wh_raises_on_missing_secret(
        self,
        bot_config: BotConfig,
    ) -> None:
        bot_manager = TelegramBotManager([bot_config])
        wh_manager = TelegramWebhookManager("https://example.com", None, bot_manager)

        with pytest.raises(ValueError, match="SECRET_TOKEN must be set"):
            await wh_manager.set_wh()

    @pytest.mark.asyncio
    async def test_set_wh_sets_webhooks_for_all_bots(
        self,
        bot_config: BotConfig,
    ) -> None:
        bot_manager = TelegramBotManager([bot_config])
        wh_manager = TelegramWebhookManager(
            "https://example.com",
            "mysecret",
            bot_manager,
        )
        bot = bot_manager.get_bot_by_connector_id(bot_config.connector_id)

        mock_delete = AsyncMock()
        mock_set = AsyncMock()
        with (
            patch.object(bot, "delete_webhook", mock_delete),
            patch.object(bot, "set_webhook", mock_set),
        ):
            await wh_manager.set_wh()

            mock_delete.assert_awaited_once_with(drop_pending_updates=False)
            mock_set.assert_awaited_once_with(
                url=f"https://example.com/ingest/incoming/telegram/{bot_config.connector_id}/webhook",
                secret_token="mysecret",
            )
