from pydantic import BaseModel, Field

from src import Settings


class BotConfig(BaseModel):
    """Connection config for a single BlueBubbles server instance.

    Unlike Telegram, there is no central platform issuing tokens — each
    BlueBubbles server is a self-hosted Mac, identified by its own URL and
    a password the operator sets locally.
    """

    connector_id: str
    server_url: str
    server_password: str
    cw_account_id: str
    cw_inbox_id: str
    send_method: str = "apple-script"  # "private-api" or "apple-script"


class IMessageSettings(Settings):
    bots_config: list[BotConfig] = Field(
        default_factory=list,
        validation_alias="IMESSAGE_BOTS_CONFIG",
    )
    channel_upload_max_mb: int = 20
    chatwoot_upload_max_mb: int = 40
    oversize_file_message: str = (
        "The file is too large to forward. Please send a smaller file."
    )
    enable_channel_delivery_confirmation: bool = False
    # BlueBubbles webhooks are configured manually in the server's UI, not via
    # an API call — see im_wh_manager.py. This is surfaced in settings so
    # on_prefork can log clear setup instructions instead of silently no-op'ing.
    webhook_path_template: str = "/ingest/incoming/imessage/{connector_id}/webhook"

    def __init__(self, **data: object) -> None:
        if "bots_config" in data and "IMESSAGE_BOTS_CONFIG" not in data:
            data["IMESSAGE_BOTS_CONFIG"] = data.pop("bots_config")
        super().__init__(**data)
