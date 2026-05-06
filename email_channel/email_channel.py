import asyncio
from typing import Any

from email_channel.email_imap_client import EmailImapClient
from email_channel.email_imap_watcher import EmailImapWatcher
from email_channel.email_message_processor import EmailMessageProcessor
from email_channel.email_routing import EmailRouting
from email_channel.email_transport import EmailTransport
from src import ChannelDeliveryResult, Envelope, IChannel


class EmailChannel(IChannel):
    channel = "email"

    def __init__(
        self,
        routing: EmailRouting,
        io_processor: EmailMessageProcessor,
        imap_watcher: EmailImapWatcher,
        transport: EmailTransport,
        imap_client: EmailImapClient,
    ) -> None:
        self._routing = routing
        self._io_processor = io_processor
        self._imap_watcher = imap_watcher
        self._transport = transport
        self._imap_client = imap_client

    def get_route_by_connector_id(self, connector_id: str) -> dict[str, str]:
        return self._routing.get_route_by_connector_id(connector_id)

    async def send_to_user(
        self, message: dict[str, Any], limiter: Any = None
    ) -> ChannelDeliveryResult:
        return await self._transport.send_to_email_user(message)

    async def build_channel_message(
        self, raw_data: dict[str, Any]
    ) -> tuple[str, Envelope]:
        return await self._io_processor.build_channel_message(raw_data)

    async def publish_channel_message(
        self, idempotency_key: str, envelope: Envelope, raw_data: dict[str, Any]
    ) -> None:
        await self._io_processor.publish_channel_message(idempotency_key, envelope)

    async def publish_chatwoot_message(
        self, raw_data: dict[str, Any], cw_account_id: str
    ) -> None:
        await self._io_processor.publish_chatwoot_message(
            raw_data,
            cw_account_id,
            self.channel,
        )

    async def on_prefork(self) -> None:
        # imaplib is synchronous and blocking; offload to a thread to avoid blocking the event loop
        await asyncio.to_thread(self._imap_client.validate_connections)

    async def on_startup(self) -> None:
        await self._imap_watcher.start()

    async def on_shutdown(self) -> None:
        await self._imap_watcher.stop()
