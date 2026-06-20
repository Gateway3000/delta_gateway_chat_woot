from pydantic import BaseModel, Field

from src import Settings


class BotConfig(BaseModel):
    """Connection config for a single Signal account.

    Signal is fronted by a `signal-bridge` container (a small presage-based
    daemon) that speaks a newline-delimited JSON protocol over TCP. Each
    "bot" is one phone `number` linked into one bridge instance, reached at
    `host`:`port`. A separate Signal number means a separate bridge instance
    (its own linked session/db), hence its own host/port here.
    """

    connector_id: str
    number: str  # the linked Signal number
    host: str  # signal-bridge hostname, e.g. "signal-bridge"
    port: int = 8080  # signal-bridge TCP port
    cw_account_id: str
    cw_inbox_id: str


class SignalSettings(Settings):
    bots_config: list[BotConfig] = Field(
        default_factory=list,
        validation_alias="SIGNAL_BOTS_CONFIG",
    )
    # How long to wait for a `send_result` from the bridge before treating a
    # send as failed (transient), and how long to wait between reconnect
    # attempts when the bridge connection drops.
    send_timeout: float = 30.0
    reconnect_delay: float = 3.0

    def __init__(self, **data: object) -> None:
        if "bots_config" in data and "SIGNAL_BOTS_CONFIG" not in data:
            data["SIGNAL_BOTS_CONFIG"] = data.pop("bots_config")
        super().__init__(**data)
