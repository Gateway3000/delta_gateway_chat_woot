from pydantic import BaseModel, Field

from src import Settings


class BotConfig(BaseModel):
    """Connection config for a single SimpleX bot profile.

    SimpleX is fronted by a `simplex-chat` CLI running as a local WebSocket
    server (exposed on the docker network via a socat shim). Each "bot" is
    one SimpleX user profile inside one such instance, reached at `ws_url`.
    `user_id` is the CLI's local user id (almost always 1 — a fresh profile
    db has a single user). A separate profile means a separate instance.
    """

    connector_id: str
    ws_url: str  # e.g. "ws://simplex-chat:5225"
    user_id: int = 1
    cw_account_id: str
    cw_inbox_id: str


class SimplexSettings(Settings):
    bots_config: list[BotConfig] = Field(
        default_factory=list,
        validation_alias="SIMPLEX_CONFIG",
    )
    # How long to wait for a command response from the CLI before treating a
    # send as failed (transient), and how long to back off between reconnects.
    send_timeout: float = 30.0
    reconnect_delay: float = 3.0

    def __init__(self, **data: object) -> None:
        if "bots_config" in data and "SIMPLEX_CONFIG" not in data:
            data["SIMPLEX_CONFIG"] = data.pop("bots_config")
        super().__init__(**data)
