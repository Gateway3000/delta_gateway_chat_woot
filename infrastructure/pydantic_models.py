from typing import Mapping, Any

from pydantic import BaseModel


class Envelope(BaseModel):
    """Unified message format for all communication channels.

    This model standardizes messages across different channels,
    enabling consistent processing and routing within the system.
    """

    id: str  # Unique message ID
    channel: str  # Channel type: "telegram", "telephony", etc.
    connector_id: str  # Connector ID
    cw_account_id: str  # Chatwoot account ID
    sender: Mapping[str, Any]  # Information about the sender
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
