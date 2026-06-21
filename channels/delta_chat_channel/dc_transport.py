from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from channels.delta_chat_channel.dc_attachments import (
    is_over_size_limit,
    resolve_delta_chat_viewtype,
)
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
        cw_session_manager: Any | None = None,
    ) -> None:
        self._settings = settings
        self._routing = routing
        self._client = client
        self._identity_store = identity_store
        self._cw_session_manager = cw_session_manager
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

    @property
    def channel_upload_max_mb(self) -> int:
        return self._settings.channel_upload_max_mb

    @property
    def chatwoot_upload_max_mb(self) -> int:
        return self._settings.chatwoot_upload_max_mb

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
            attachments = list(envelope.payload.get("attachments") or [])

            async def _download_attachment(
                attachment: dict[str, Any],
            ) -> tuple[str, str, Any | None]:
                url = attachment.get("data_url") or attachment.get("url")
                if not url:
                    raise FatalError("Missing attachment URL")
                url = self._resolve_attachment_url(str(url))
                if self._cw_session_manager is None:
                    raise FatalError("Chatwoot HTTP session is not available")

                size = attachment.get("size")
                if is_over_size_limit(
                    int(size) if size is not None else None,
                    self._settings.chatwoot_upload_max_mb,
                ):
                    raise FatalError("Attachment exceeds configured size limit")

                filename = str(
                    attachment.get("filename")
                    or attachment.get("file_name")
                    or Path(urlsplit(url).path).name
                    or "attachment"
                )
                viewtype = resolve_delta_chat_viewtype(attachment)
                suffix = Path(filename).suffix or ""
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                    temp_path = tmp_file.name

                session = self._cw_session_manager.session
                try:
                    async with session.get(url) as response:
                        if response.status >= 400:
                            response_text = await response.text()
                            raise FatalError(
                                f"Chatwoot attachment download failed {response.status}: {response_text[:200]}"
                            )
                        downloaded = 0
                        with open(temp_path, "wb") as file_handle:
                            async for chunk in response.content.iter_chunked(64 * 1024):
                                downloaded += len(chunk)
                                if is_over_size_limit(
                                    downloaded, self._settings.chatwoot_upload_max_mb
                                ):
                                    raise FatalError(
                                        "Attachment exceeds configured size limit"
                                    )
                                file_handle.write(chunk)
                except Exception:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    raise

                return temp_path, filename, viewtype

            prepared_attachments: list[tuple[str, str, Any | None]] = []
            for attachment in attachments:
                prepared_attachments.append(await _download_attachment(attachment))

            def _deliver() -> None:
                contact = account.get_contact_by_addr(external_address)
                if contact is None:
                    contact = account.create_contact(
                        external_address, envelope.sender.name
                    )
                chat = account.get_chat_by_contact(contact) or contact.create_chat()
                if prepared_attachments:
                    text_to_send = payload_text or None
                    for index, (temp_path, filename, viewtype) in enumerate(
                        prepared_attachments
                    ):
                        if text_to_send is not None and index == 0:
                            chat.send_message(
                                text=text_to_send,
                                file=temp_path,
                                filename=filename,
                                viewtype=viewtype,
                            )
                        else:
                            chat.send_message(
                                file=temp_path,
                                filename=filename,
                                viewtype=viewtype,
                            )
                    return
                if payload_text:
                    chat.send_message(text=payload_text)

            try:
                await asyncio.to_thread(_deliver)
            finally:
                for temp_path, _, _ in prepared_attachments:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
            return ChannelDeliveryResult(
                ok=True,
                external_id=external_address,
            )
        except FatalError:
            raise
        except ValueError as exc:
            raise FatalError(str(exc)) from exc
        except Exception as exc:
            raise TransientError(f"Delta Chat delivery failed: {exc}") from exc

    def _resolve_attachment_url(self, url: str) -> str:
        parsed = urlsplit(url)
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return url

        chatwoot_base_url = self._settings.chatwoot_base_url.rstrip("/")
        if not chatwoot_base_url:
            return url
        base = urlsplit(chatwoot_base_url)
        return urlunsplit(
            (base.scheme, base.netloc, parsed.path, parsed.query, parsed.fragment)
        )

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
