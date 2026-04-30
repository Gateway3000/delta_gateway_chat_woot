from typing import Mapping, Any, Literal

from pydantic import BaseModel

SenderInfoKey = Literal["external_id", "name", "nickname"]


class SenderInfo(BaseModel):
    """Information about the message sender in a communication channel."""

    external_id: str | int
    name: str | None = None
    nickname: str | None = None

    def __getitem__(self, key: SenderInfoKey) -> Any:
        return getattr(self, key)


class Envelope(BaseModel):
    """Unified message format for all communication channels."""

    idem_key: str
    channel: str
    from_: str
    to: str
    connector_id: str
    cw_inbox_id: str = ""
    message_id: str = ""
    cw_account_id: str
    sender: SenderInfo
    payload: Mapping[str, Any]
    ts: float


class ChannelDeliveryResult(BaseModel):
    """Represents the result of sending a Chatwoot -> Channel message."""

    ok: bool
    external_id: str | None = None
    retry_after: float | None = None
    error: str | None = None
