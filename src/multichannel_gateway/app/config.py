from enum import Enum

from dotenv import load_dotenv, find_dotenv
from pydantic_settings import BaseSettings

load_dotenv(find_dotenv(".env"))


class Environment(str, Enum):
    DEV = "DEV"
    STAGE = "STAGE"
    PROD = "PROD"
    LOCAL = "LOCAL"


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

    secret_token: str | None = None

    chatwoot_access_token: str = ""
    chatwoot_base_url: str = ""

    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"

    workers: int = 1

    @property
    def db_url(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_pass}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )
