from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DeltaChatAccountConfig(BaseModel):
    connector_id: str
    address: str
    password: str
    display_name: str | None = None
    avatar_path: str | None = None
    bridge_url: str | None = None
    cw_account_id: str
    cw_inbox_id: str
    storage_dir: str | None = None


class DeltaChatRuntimeAccount(BaseModel):
    connector_id: str
    account_id: int
    address: str
    storage_dir: str


class DeltaChatIncomingMessage(BaseModel):
    account_id: int
    connector_id: str | None = None
    message_id: str
    chat_id: str
    sender_id: str
    sender_address: str
    sender_name: str | None = None
    text: str = ""
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    is_group: bool = False
    is_info: bool = False

    def resolved_attachments(self) -> list[dict[str, Any]]:
        return list(self.attachments)
