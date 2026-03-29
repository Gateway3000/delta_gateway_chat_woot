from pydantic import BaseModel


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
