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

    anonymize_users: bool = False

    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"

    workers: int = 1

    channels: list[str] = []

    @property
    def db_url(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_pass}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


class TelemetrySettings(BaseSettings):
    otel_enabled: bool = True
    otel_service_name: str = "channel_gateway"
    otel_endpoint: str | None = None
    otel_insecure: bool = True
    otel_sampling_ratio: float = 1.0
    sentry_dsn: str | None = None
    environment: Environment = Environment.LOCAL
    sentry_release: str | None = None
    sentry_traces_sample_rate: float = 1.0
    sentry_send_default_pii: bool = False
