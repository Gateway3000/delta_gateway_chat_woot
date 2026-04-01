import asyncio
from typing import Any

from aiogram import Dispatcher, Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import Update
from aiohttp import ClientConnectorError, ServerDisconnectedError

from src import DeliveryResult, Envelope
from src.multichannel_gateway.core.exceptions import (
    RateLimitError,
    FatalError,
    TransientError,
)
from telegram.tg_bot_manager import TelegramBotManager


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
        self, message: dict[str, Any], limiter: Any = asyncio.sleep
    ) -> DeliveryResult:
        envelope = Envelope.model_validate(message)
        connector_id = envelope.connector_id
        bot = self._bots.get_bot_by_connector_id(connector_id)
        try:
            await limiter(0.3)
            msg = await bot.send_message(
                chat_id=envelope.sender["external_id"],
                text=envelope.payload["text"],
            )
            return DeliveryResult(ok=True, external_id=str(msg.message_id))

        except (
            TelegramNetworkError,
            ClientConnectorError,
            TimeoutError,
            ServerDisconnectedError,
        ) as exc:
            raise TransientError(
                f"Telegram transient delivery failure: {repr(exc)}"
            ) from exc

        except TelegramRetryAfter as exc:
            raise RateLimitError from exc
        except TelegramAPIError as exc:
            retry_after = getattr(exc, "retry_after", None)
            if retry_after is not None:
                raise TransientError(
                    f"Telegram rate limited: retry after {retry_after}s ({repr(exc)})"
                ) from exc
            raise FatalError(f"Telegram delivery failure: {repr(exc)}") from exc

        except Exception as exc:
            raise FatalError(f"Telegram delivery failure: {repr(exc)}") from exc
