from typing import Any

from src.multichannel_gateway.core import generate_username
from src.multichannel_gateway.core.interfaces.envelope_factory import IEnvelopeFactory
from src.multichannel_gateway.infrastructure import ChannelRegistry, ContactAliasStore


class ChannelToChatwootOrchestrator:
    def __init__(
        self,
        registry: ChannelRegistry,
        anonymize_users: bool,
        alias_store: ContactAliasStore,
    ) -> None:
        self._registry = registry
        self._anonymize_users = anonymize_users
        self._alias_store = alias_store

    async def process(self, channel_name: str, raw_data: dict[str, Any]) -> None:
        channel = self._registry.get_channel(channel_name)
        idempotency_key, envelope = await channel.build_channel_message(raw_data)

        raw_id = envelope.sender.external_id
        envelope.sender.raw_external_id = raw_id

        if self._anonymize_users:
            envelope.sender.external_id = await self._alias_store.get_or_create_alias(
                channel_name, str(raw_id)
            )
            envelope.sender.name = generate_username()[0]
        else:
            envelope.sender.external_id = IEnvelopeFactory._add_channel_prefix(
                raw_id, channel_name
            )

        await channel.publish_channel_message(idempotency_key, envelope, raw_data)
