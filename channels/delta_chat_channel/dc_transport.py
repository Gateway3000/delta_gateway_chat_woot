from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from channels.delta_chat_channel.dc_client import DeltaChatClient
from channels.delta_chat_channel.dc_routing import DeltaChatRouting
from channels.delta_chat_channel.dc_settings import DeltaChatSettings
from src import ChannelDeliveryResult, Envelope
from src.multichannel_gateway.core.exceptions import FatalError, TransientError
from src.multichannel_gateway.infrastructure.identity_store import IdentityStore


class DeltaChatTransport:
    def __init__(
        self,
        settings: DeltaChatSettings,
        routing: DeltaChatRouting,
        client: DeltaChatClient,
        identity_store: IdentityStore,
    ) -> None:
        self._settings = settings
        self._routing = routing
        self._client = client
        self._identity_store = identity_store
        self._legacy_bridge_enabled = not settings.enable_native_deltachat_channel
        if settings.enable_native_deltachat_channel:
            bridge_configs = [
                cfg.connector_id
                for cfg in settings.delta_chat_accounts
                if cfg.bridge_url
            ]
            if bridge_configs:
                raise ValueError(
                    "bridge_url is not allowed when ENABLE_NATIVE_DELTACHAT_CHANNEL=true "
                    f"(connectors: {', '.join(bridge_configs)})"
                )

    async def send_to_delta_chat_user(
        self, message: dict[str, Any]
    ) -> ChannelDeliveryResult:
        envelope = Envelope.model_validate(message)
        route = self._routing.get_route_by_connector_id(envelope.connector_id)

        actor_id = str(envelope.sender.external_id)
        external_address = str(
            envelope.sender.raw_external_id
            or await self._identity_store.resolve_external_id("delta_chat", actor_id)
        )
        payload_text = str(envelope.payload.get("text") or "")
        attachments = list(envelope.payload.get("attachments") or [])
        bridge_url = str(route.get("bridge_url") or "").rstrip("/")

        if self._legacy_bridge_enabled:
            if not bridge_url:
                raise FatalError("Delta Chat bridge is disabled and no bridge_url is configured")
            return await self._send_via_bridge(
                bridge_url=bridge_url,
                actor_id=actor_id,
                external_address=external_address,
                conversation_id=str(envelope.payload.get("conversation_id") or ""),
                message_id=envelope.message_id,
                text=payload_text,
                attachments=attachments,
            )

        try:
            account = self._client.get_account(route["connector_id"])

            def _deliver() -> None:
                contact = account.create_contact(external_address, envelope.sender.name)
                chat = contact.create_chat()
                if payload_text:
                    chat.send_text(payload_text)
                for attachment in attachments:
                    file_path = attachment.get("path") or attachment.get("file_path")
                    if file_path:
                        chat.send_file(str(file_path))

            await asyncio.to_thread(_deliver)
            return ChannelDeliveryResult(
                ok=True,
                external_id=external_address,
            )
        except ValueError as exc:
            raise FatalError(str(exc)) from exc
        except Exception as exc:
            raise TransientError(f"Delta Chat delivery failed: {exc}") from exc

    async def _send_via_bridge(
        self,
        *,
        bridge_url: str,
        actor_id: str,
        external_address: str,
        conversation_id: str,
        message_id: str,
        text: str,
        attachments: list[dict[str, Any]],
    ) -> ChannelDeliveryResult:
        payload = {
            "actor_id": actor_id,
            "external_id": external_address,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "text": text,
            "attachments": attachments,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{bridge_url}/send", json=payload) as response:
                    if response.status >= 500:
                        text_response = await response.text()
                        raise TransientError(
                            f"Delta Chat bridge error {response.status} for {external_address}: {text_response}"
                        )
                    if response.status >= 400:
                        text_response = await response.text()
                        raise FatalError(
                            f"Delta Chat bridge fatal error {response.status} for {external_address}: {text_response}"
                        )
            return ChannelDeliveryResult(ok=True, external_id=external_address)
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise TransientError(f"Delta Chat bridge delivery failed: {exc}") from exc
