from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.methods import SendMessage
from aiogram.types import Message

from src import DeliveryResult
from src.multichannel_gateway.core.exceptions import (
    FatalError,
    RateLimitError,
    TransientError,
)
from telegram.tg_bot_manager import TelegramBotManager
from telegram.tg_gateway import TelegramGateway
from telegram.tg_transport import TelegramTransport


def _build_bot_manager(bot: Bot) -> TelegramBotManager:
    bot_manager = Mock(spec=TelegramBotManager)
    bot_manager.get_bot_by_connector_id.return_value = bot
    return cast(TelegramBotManager, bot_manager)


def _build_message() -> dict[str, object]:
    return {
        "idem_key": "chatwoot->telegram:tg1:token:123321:60538",
        "channel": "telegram",
        "from_": "chatwoot",
        "to": "telegram",
        "connector_id": "tg1",
        "cw_inbox_id": "18",
        "message_id": "60538",
        "cw_account_id": "3",
        "sender": {"external_id": "123321"},
        "payload": {"text": "Test message from Chatwoot!"},
        "ts": 1.0,
    }


def _build_attachment_message(text: str) -> dict[str, object]:
    message = _build_message()
    message["payload"] = {
        "text": text,
        "attachments": [
            {
                "file_type": "image",
                "data_url": "https://example.com/image.jpg",
            }
        ],
    }
    return message


def _build_gateway(transport: TelegramTransport) -> TelegramGateway:
    return TelegramGateway(
        cast(TelegramBotManager, Mock()),
        Mock(),
        transport,
        Mock(),
        Mock(),
        Mock(),
    )


@pytest.mark.asyncio
async def test_send_to_user_returns_failed_result_on_telegram_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = Bot("123456:ABCDEF")
    transport = TelegramTransport(_build_bot_manager(bot), Mock())
    api_error = TelegramAPIError(
        SendMessage(chat_id=123321, text="Test message from Chatwoot!"),
        "telegram api failed",
    )
    mock_send_message = AsyncMock(side_effect=api_error)

    monkeypatch.setattr("aiogram.client.bot.Bot.send_message", mock_send_message)

    try:
        with pytest.raises(FatalError) as exc_info:
            await transport.send_to_user(_build_message())
    finally:
        await bot.session.close()

    assert str(exc_info.value) == f"Telegram delivery failure: {repr(api_error)}"
    mock_send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_to_user_raises_fatal_error_on_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = Bot("123456:ABCDEF")
    transport = TelegramTransport(_build_bot_manager(bot), Mock())
    limiter = AsyncMock()
    unexpected_error = Exception("unexpected telegram failure")
    mock_send_message = AsyncMock(side_effect=unexpected_error)

    monkeypatch.setattr("aiogram.client.bot.Bot.send_message", mock_send_message)

    try:
        with pytest.raises(FatalError) as exc_info:
            await transport.send_to_user(_build_message(), limiter=limiter)
    finally:
        await bot.session.close()

    assert str(exc_info.value) == f"Telegram delivery failure: {repr(unexpected_error)}"
    limiter.assert_awaited_once_with(0.3)
    mock_send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_to_user_raises_rate_limit_error_on_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = Bot("123456:ABCDEF")
    transport = TelegramTransport(_build_bot_manager(bot), Mock())

    api_error = TelegramRetryAfter(
        SendMessage(chat_id=123321, text="Test message from Chatwoot!"),
        "too many requests",
        retry_after=12,
    )
    mock_send_message = AsyncMock(side_effect=api_error)

    monkeypatch.setattr("aiogram.client.bot.Bot.send_message", mock_send_message)

    try:
        with pytest.raises(RateLimitError):
            await transport.send_to_user(_build_message())
    finally:
        await bot.session.close()

    mock_send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_gateway_send_to_user_proxies_transport_result() -> None:
    transport_mock = Mock(spec=TelegramTransport)
    transport_mock.send_to_user = AsyncMock(
        return_value=DeliveryResult(ok=True, external_id="123")
    )
    gateway = _build_gateway(cast(TelegramTransport, transport_mock))

    result = await gateway.send_to_user(_build_message())

    assert result.ok is True
    assert result.external_id == "123"
    transport_mock.send_to_user.assert_awaited_once_with(_build_message())


@pytest.mark.asyncio
async def test_send_to_user_raises_transient_error_on_network_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = Bot("123456:ABCDEF")
    transport = TelegramTransport(_build_bot_manager(bot), Mock())
    network_error = TelegramNetworkError(
        method=SendMessage(chat_id=123321, text="Test message from Chatwoot!"),
        message=(
            "HTTP Client says - ClientConnectorError: Cannot connect to host "
            "api.telegram.org:443 ssl:default [None]"
        ),
    )
    mock_send_message = AsyncMock(side_effect=network_error)

    monkeypatch.setattr("aiogram.client.bot.Bot.send_message", mock_send_message)

    try:
        with pytest.raises(TransientError) as exc_info:
            await transport.send_to_user(_build_message())
    finally:
        await bot.session.close()

    assert (
        str(exc_info.value)
        == f"Telegram transient delivery failure: {repr(network_error)}"
    )
    mock_send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_to_user_skips_whitespace_only_text_and_sends_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = Bot("123456:ABCDEF")
    transport = TelegramTransport(_build_bot_manager(bot), Mock())
    mock_send_message = AsyncMock()
    sent_photo_message = cast(Message, Mock(message_id=777))
    mock_send_photo = AsyncMock(return_value=sent_photo_message)

    monkeypatch.setattr("aiogram.client.bot.Bot.send_message", mock_send_message)
    monkeypatch.setattr("aiogram.client.bot.Bot.send_photo", mock_send_photo)

    try:
        result = await transport.send_to_user(_build_attachment_message("   \n\t"))
    finally:
        await bot.session.close()

    assert result.ok is True
    assert result.external_id == "777"
    mock_send_message.assert_not_awaited()
    mock_send_photo.assert_awaited_once()
