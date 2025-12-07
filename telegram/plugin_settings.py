from pydantic import BaseModel

from src import Settings


class BotConfig(BaseModel):
    connector_id: str
    bot_token: str
    cw_account_id: str
    cw_inbox_id: str


class TelegramSettings(Settings):
    bots_config: list[BotConfig] = []
