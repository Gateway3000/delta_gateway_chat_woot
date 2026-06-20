from pydantic import BaseModel

from src import Settings


class WhatsAppConnector(BaseModel):
    connector_id: str
    sidecar_url: str  # e.g. http://wa-sidecar-1:3000
    cw_account_id: str
    cw_inbox_id: str


class WhatsAppSettings(Settings):
    # Reads env WHATSAPP_CONFIG (JSON list), like BOTS_CONFIG for Telegram.
    whatsapp_config: list[WhatsAppConnector] = []
    sidecar_token: str = ""  # bearer token for the sidecar /send endpoint
    chatwoot_upload_max_mb: int = 40
    send_timeout_seconds: float = 30.0
