from typing import Any

from src.multichannel_gateway.core import generate_username
from src.multichannel_gateway.infrastructure import ChannelRegistry


class ChannelToChatwootOrchestrator:
    def __init__(
        self,
        registry: ChannelRegistry,
        anonymize_users: bool,
    ) -> None:
        self._registry = registry
        self._anonymize_users = anonymize_users

    async def process(self, channel_name: str, raw_data: dict[str, Any]) -> None:
        channel = self._registry.get_channel(channel_name)
        idempotency_key, envelope = await channel.build_channel_message(raw_data)
        if self._anonymize_users:
            envelope.sender.name = generate_username()[0]

        await channel.publish_channel_message(idempotency_key, envelope, raw_data)
