from pydantic import BaseModel

from src import Settings


class BotConfig(BaseModel):
    connector_id: str
    bot_token: str
    cw_account_id: str
    cw_inbox_id: str


class TelegramSettings(Settings):
    bots_config: list[BotConfig] = []
    channel_upload_max_mb: int = 20
    chatwoot_upload_max_mb: int = 40
    oversize_file_message: str = (
        "The file is too large to forward. Please send a smaller file."
    )
    enable_channel_delivery_confirmation: bool = False
