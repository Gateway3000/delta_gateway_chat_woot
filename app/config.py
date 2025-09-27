from dotenv import load_dotenv, find_dotenv
from pydantic import BaseModel
from pydantic_settings import BaseSettings

load_dotenv(find_dotenv(".env"))


class BotConfig(BaseModel):
    connector_id: str
    bot_token: str
    cw_account_id: str


class Settings(BaseSettings):
    db_user: str | None = None
    db_pass: str | None = None
    db_host: str | None = None
    db_port: int = 5432
    db_name: str | None = None

    incoming_queue_name: str = "to_cw"
    outgoing_queue_name: str = "from_cw"

    wh_domain: str | None = None

    group: str = ""

    secret_key: str | None = None
    algorithm: str | None = None

    bots_config: list[BotConfig] = []
    secret_token: str | None = None

    environment: str = "DEVELOPMENT"
    log_level: str = "INFO"

    @property
    def db_url(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_pass}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )
