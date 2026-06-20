from typing import Any

import asyncio

from channels.delta_chat_channel.dc_client import DeltaChatClient
from channels.delta_chat_channel.dc_message_processor import DeltaChatMessageProcessor
from channels.delta_chat_channel.dc_routing import DeltaChatRouting
from channels.delta_chat_channel.dc_transport import DeltaChatTransport
from src import ChannelDeliveryResult, Envelope, IChannel


class DeltaChatChannel(IChannel):
    channel = "delta_chat"

    def __init__(
        self,
        routing: DeltaChatRouting,
        client: DeltaChatClient,
        transport: DeltaChatTransport,
        io_processor: DeltaChatMessageProcessor,
    ) -> None:
        self._routing = routing
        self._client = client
        self._transport = transport
        self._io_processor = io_processor

    async def on_startup(self) -> None:
        if not self._client.is_native_enabled:
            return

        loop = asyncio.get_running_loop()

        def _dispatch(_runtime_account: Any, payload: dict[str, Any]) -> None:
            asyncio.run_coroutine_threadsafe(
                self._publish_incoming(payload), loop
            )

        self._client.register_message_handler(_dispatch)
        await asyncio.to_thread(self._client.start)

    async def on_shutdown(self) -> None:
        if not self._client.is_native_enabled:
            return
        await asyncio.to_thread(self._client.stop)

    def get_route_by_connector_id(self, connector_id: str) -> dict[str, str]:
        return self._routing.get_route_by_connector_id(connector_id)

    async def send_to_user(
        self, message: dict[str, Any], limiter: Any = None
    ) -> ChannelDeliveryResult:
        return await self._transport.send_to_delta_chat_user(message)

    async def build_channel_message(
        self, raw_data: dict[str, Any]
    ) -> tuple[str, Envelope]:
        return await self._io_processor.build_channel_message(raw_data)

    async def publish_channel_message(
        self, idempotency_key: str, envelope: Envelope, raw_data: dict[str, Any]
    ) -> None:
        await self._io_processor.publish_channel_message(
            idempotency_key, envelope, raw_data
        )

    async def publish_chatwoot_message(
        self, raw_data: dict[str, Any], cw_account_id: str
    ) -> None:
        await self._io_processor.publish_chatwoot_message(raw_data, cw_account_id)

    async def _publish_incoming(self, payload: dict[str, Any]) -> None:
        idempotency_key, envelope = await self._io_processor.build_channel_message(
            payload
        )
        await self._io_processor.publish_channel_message(
            idempotency_key, envelope, payload
        )
