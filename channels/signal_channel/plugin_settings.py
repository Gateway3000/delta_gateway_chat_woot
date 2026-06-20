from pydantic import BaseModel, Field

from src import Settings


class BotConfig(BaseModel):
    """Connection config for a single Signal account.

    Signal runs inside a `signal-cli-rest-api` container. Unlike Telegram
    (a central platform issuing bot tokens), each "bot" here is one phone
    `number` already registered/linked in that container, reachable at
    `api_url`. A single container can host several numbers, so `api_url`
    may be shared across connectors while `number` is what distinguishes
    the account.
    """

    connector_id: str
    number: str  # the registered Signal number, e.g. "+4917624102926"
    api_url: str  # signal-cli-rest-api base URL, e.g. "http://signal:8080"
    cw_account_id: str
    cw_inbox_id: str


class SignalSettings(Settings):
    bots_config: list[BotConfig] = Field(
        default_factory=list,
        validation_alias="SIGNAL_BOTS_CONFIG",
    )
    # signal-cli-rest-api does not push webhooks; we long-poll
    # `GET /v1/receive/{number}`. `receive_timeout` is the server-side
    # long-poll window (seconds) and `receive_poll_delay` is how long we
    # back off before re-polling after an empty result or a network blip.
    receive_timeout: int = 10
    receive_poll_delay: float = 1.0
    receive_error_backoff: float = 5.0

    def __init__(self, **data: object) -> None:
        if "bots_config" in data and "SIGNAL_BOTS_CONFIG" not in data:
            data["SIGNAL_BOTS_CONFIG"] = data.pop("bots_config")
        super().__init__(**data)
