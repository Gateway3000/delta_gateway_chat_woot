import asyncio
from typing import Any

from aiogram import Dispatcher, Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Update

from infrastructure.pydantic_models import Envelope, DeliveryResult
from infrastructure.telegram.tg_bot_manager import TelegramBotManager


class TelegramTransport:
    """Handles sending and receiving messages through Telegram bots.

    This class acts as a transport layer between the system and Telegram,
    providing methods to send messages to users and feed inbound updates
    into the dispatcher.
    """

    def __init__(self, bot_manager: TelegramBotManager, dp: Dispatcher):
        self._bots = bot_manager
        self._dp = dp

    async def send_to_telegram(self, bot: Bot, raw_data: dict[str, Any]) -> None:
        update = Update.model_validate(raw_data)
        await self._dp.feed_update(bot, update)

    async def send_to_user(
        self, message: str, limiter: Any = asyncio.sleep
    ) -> DeliveryResult:
        envelope = Envelope.model_validate_json(message)
        connector_id = envelope.connector_id
        bot = self._bots.get_bot_by_connector_id(connector_id)
        try:
            await limiter(0.3)
            msg = await bot.send_message(
                chat_id=envelope.sender["external_id"],
                text=envelope.payload["text"],
            )
            return DeliveryResult(ok=True, external_id=str(msg.message_id))

        except TelegramAPIError as e:
            retry_after = getattr(e, "retry_after", None)
            return DeliveryResult(ok=False, retry_after=retry_after, error=str(e))

        except Exception as e:
            return DeliveryResult(ok=False, error=str(e))
