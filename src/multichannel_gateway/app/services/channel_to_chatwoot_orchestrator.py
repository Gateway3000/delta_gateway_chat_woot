from typing import Any

from src.multichannel_gateway.core import generate_username
from src.multichannel_gateway.core.interfaces.envelope_factory import IEnvelopeFactory
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

        raw_id = envelope.sender.external_id
        if envelope.sender.raw_external_id is None and channel_name != "delta_chat":
            envelope.sender.raw_external_id = raw_id
        if channel_name != "delta_chat":
            envelope.sender.external_id = IEnvelopeFactory._add_channel_prefix(
                raw_id, channel_name
            )

        if self._anonymize_users:
            envelope.sender.name = generate_username()[0]

        await channel.publish_channel_message(idempotency_key, envelope, raw_data)
