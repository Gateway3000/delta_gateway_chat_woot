from telegram.tg_bot_manager import TelegramBotManager


class TelegramWebhookManager:
    def __init__(
        self,
        wh_domain: str | None,
        secret_token: str | None,
        bot_manager: TelegramBotManager,
    ):
        self._wh_domain = wh_domain
        self._secret_token = secret_token
        self._bots = bot_manager

    async def set_wh(self) -> None:
        if not self._wh_domain:
            raise ValueError("WH_DOMAIN must be set")
        if not self._secret_token:
            raise ValueError("SECRET_TOKEN must be set")

        for cid, bot in self._bots.bots.items():
            await bot.delete_webhook(drop_pending_updates=True)
            webhook_url = f"{self._wh_domain}/ingest/incoming/telegram/{cid}/webhook"
            await bot.set_webhook(
                url=webhook_url,
                secret_token=self._secret_token,
            )
            await bot.session.close()
