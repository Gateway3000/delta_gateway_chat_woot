from __future__ import annotations

import os
from typing import Any

import requests


class GatewayClient:
    def __init__(
        self, base_url: str, connector_id: str, token: str | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.connector_id = connector_id
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def post_inbound(
        self,
        *,
        external_id: str,
        conversation_id: str,
        text: str,
        attachments: list[dict[str, Any]] | None = None,
        message_id: str | None = None,
        name: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "channel": "delta_chat",
            "connector_id": self.connector_id,
            "external_id": external_id,
            "conversation_id": conversation_id,
            "text": text,
            "attachments": attachments or [],
            "message_id": message_id,
            "name": name,
        }
        response = requests.post(
            f"{self.base_url}/messages/inbound",
            json=payload,
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()

    def post_outbound(
        self,
        *,
        cw_account_id: str,
        payload: dict[str, Any],
    ) -> None:
        body = dict(payload)
        body["channel"] = "delta_chat"
        body["cw_account_id"] = cw_account_id
        response = requests.post(
            f"{self.base_url}/messages/outbound",
            json=body,
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()


def get_gateway() -> GatewayClient:
    base_url = os.getenv("GATEWAY_BASE_URL", "http://host.docker.internal:8080")
    connector_id = os.getenv("GATEWAY_CONNECTOR_ID", "delta-chat-local")
    token = os.getenv("GATEWAY_TOKEN") or None
    return GatewayClient(base_url, connector_id, token)
