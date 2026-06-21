from pydantic import BaseModel, Field

from src import Settings

BOT_SOURCE = "session_bot"


class BotConfig(BaseModel):
    connector_id: str
    webhook_url: str
    cw_account_id: str
    cw_inbox_id: str


class SessionSettings(Settings):
    bots_config: list[BotConfig] = Field(
        default_factory=list,
        validation_alias="SESSION_BOTS_CONFIG",
    )
    bot_source_name: str = BOT_SOURCE
    request_timeout_seconds: float = 10.0

    def __init__(self, **data: object) -> None:
        if "bots_config" in data and "SESSION_BOTS_CONFIG" not in data:
            data["SESSION_BOTS_CONFIG"] = data.pop("bots_config")
        super().__init__(**data)  # type: ignore[arg-type]

