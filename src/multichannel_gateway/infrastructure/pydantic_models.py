from typing import Mapping, Any, Literal

from pydantic import BaseModel

SenderInfoKey = Literal["external_id", "name", "nickname"]


class SenderInfo(BaseModel):
    """Unified message format for all communication channels.

    This model standardizes messages across different channels,
    enabling consistent processing and routing within the system.
    """

    external_id: str | int  # Message ID in the channel
    name: str | None = None  # Users name
    nickname: str | None = None  # Users nickname

    def __getitem__(self, key: SenderInfoKey) -> Any:
        return getattr(self, key)


class Envelope(BaseModel):
    """Unified message format for all communication channels.

    This model standardizes messages across different channels,
    enabling consistent processing and routing within the system.
    """

    idem_key: str  # Unique idempotency key
    channel: str  # Channel type: "telegram", "telephony", etc.
    from_: str  # Which channel the message came from
    to: str  # Which channel the message was sent to
    connector_id: str  # Connector ID
    cw_inbox_id: str = ""  # Chatwoot inbox ID
    message_id: str = ""  # Unique message ID
    cw_account_id: str  # Chatwoot account ID
    sender: SenderInfo  # Information about the sender
    payload: Mapping[str, Any]  # Message content
    ts: float  # Timestamp


class DeliveryResult(BaseModel):
    """Represents the result of sending an outbound message.

    This model captures delivery status, any associated external message ID,
    retry information, and error details if the delivery failed.
    """

    ok: bool  # Whether the message was successfully delivered
    external_id: str | None = None  # Message ID in the channel
    retry_after: float | None = None  # Delay before retrying (in seconds)
    error: str | None = None  # Description of the error, if any


class ContactInfo(BaseModel):
    """Flattened Chatwoot contact response."""

    contact_id: int
    email: str | None
    name: str
    phone_number: str | None
    identifier: str | None
    source_id: str
    inbox_id: int


class ContactSearchResult(BaseModel):
    """Flattened search result for a Chatwoot contact."""

    contact_id: int
    name: str
    email: str | None
    phone_number: str | None
    source_id: str
    inbox_id: int
