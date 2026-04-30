import asyncio
from typing import Any

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import URLInputFile
from aiohttp import ClientConnectorError, ServerDisconnectedError

from src import ChannelDeliveryResult, Envelope
from src.multichannel_gateway.core.exceptions import (
    RateLimitError,
    FatalError,
    TransientError,
)
from telegram.tg_bot_manager import TelegramBotManager


class TelegramTransport:
    """Handles sending messages to Telegram users."""

    def __init__(self, bot_manager: TelegramBotManager):
        self._bots = bot_manager

    async def send_to_telegram_user(
        self, message: dict[str, Any], limiter: Any = asyncio.sleep
    ) -> ChannelDeliveryResult:
        envelope = Envelope.model_validate(message)
        connector_id = envelope.connector_id
        bot = self._bots.get_bot_by_connector_id(connector_id)
        text = str(envelope.payload.get("text") or "").strip()
        attachments = envelope.payload.get("attachments", [])
        sent_message_ids: list[str] = []
        try:
            await limiter(0.3)
            if text:
                msg = await bot.send_message(
                    chat_id=envelope.sender["external_id"],
                    text=text,
                )
                sent_message_ids.append(str(msg.message_id))

            for attachment in attachments:
                data_url = attachment.get("data_url")
                if not data_url:
                    continue

                input_file = URLInputFile(data_url)
                file_type = attachment.get("file_type", "file")
                if file_type == "image":
                    sent = await bot.send_photo(
                        chat_id=envelope.sender["external_id"],
                        photo=input_file,
                    )
                elif file_type == "video":
                    sent = await bot.send_video(
                        chat_id=envelope.sender["external_id"],
                        video=input_file,
                    )
                elif file_type == "audio":
                    sent = await bot.send_audio(
                        chat_id=envelope.sender["external_id"],
                        audio=input_file,
                    )
                else:
                    sent = await bot.send_document(
                        chat_id=envelope.sender["external_id"],
                        document=input_file,
                    )
                sent_message_ids.append(str(sent.message_id))

            if not sent_message_ids:
                raise FatalError("Telegram delivery failure: no text or attachments")

            return ChannelDeliveryResult(
                ok=True, external_id=",".join(sent_message_ids)
            )

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
            retry_after = getattr(
                exc, "retry_after", RateLimitError.DEFAULT_RETRY_AFTER_SECONDS
            )
            raise RateLimitError(
                f"Telegram rate limited: retry after {retry_after}s ({repr(exc)})",
                retry_after_seconds=retry_after,
            ) from exc

        except TelegramAPIError as exc:
            retry_after = getattr(exc, "retry_after", None)
            if retry_after is not None:
                raise RateLimitError(
                    f"Telegram rate limited: retry after {retry_after}s ({repr(exc)})",
                    retry_after_seconds=retry_after,
                ) from exc
            raise FatalError(f"Telegram delivery failure: {repr(exc)}") from exc

        except Exception as exc:
            raise FatalError(f"Telegram delivery failure: {repr(exc)}") from exc
