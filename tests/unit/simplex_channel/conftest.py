import pytest

from channels.simplex_channel.plugin_settings import BotConfig, SimplexSettings
from channels.simplex_channel.sx_envelope_factory import SimplexEnvelopeFactory
from channels.simplex_channel.sx_routing import SimplexRouting


@pytest.fixture
def bot_config() -> BotConfig:
    return BotConfig(
        connector_id="sx1",
        ws_url="ws://simplex-chat:5225",
        user_id=1,
        cw_account_id="1",
        cw_inbox_id="5",
    )


@pytest.fixture
def settings(bot_config: BotConfig) -> SimplexSettings:
    return SimplexSettings(bots_config=[bot_config])


@pytest.fixture
def routing(bot_config: BotConfig) -> SimplexRouting:
    return SimplexRouting([bot_config])


@pytest.fixture
def envelope_factory(routing: SimplexRouting) -> SimplexEnvelopeFactory:
    return SimplexEnvelopeFactory(routing)


def make_message(
    *,
    source_id: int = 42,
    source_name: str | None = "Alice",
    text: str = "Hi",
    item_id: int = 1001,
    connector_id: str = "sx1",
) -> dict:
    """Build a normalized SimpleX message event as the receiver hands it to the factory."""
    return {
        "type": "message",
        "source_id": source_id,
        "source_name": source_name,
        "item_id": item_id,
        "text": text,
        "channel": "simplex",
        "connector_id": connector_id,
    }


def make_new_chat_items_event(
    *,
    chat_type: str = "direct",
    dir_type: str = "directRcv",
    content_type: str = "text",
    text: str = "Hi",
    contact_id: int = 42,
    item_id: int = 1001,
) -> dict:
    """Build a raw simplex-chat `newChatItems` event payload (post-_unwrap_event)."""
    return {
        "type": "newChatItems",
        "chatItems": [
            {
                "chatInfo": {
                    "type": chat_type,
                    "contact": {"contactId": contact_id, "localDisplayName": "alice"},
                },
                "chatItem": {
                    "chatDir": {"type": dir_type},
                    "meta": {"itemId": item_id},
                    "content": {"msgContent": {"type": content_type, "text": text}},
                },
            }
        ],
    }
