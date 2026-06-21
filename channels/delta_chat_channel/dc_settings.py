from pydantic import Field

from src import Settings

from .dc_models import DeltaChatAccountConfig


class DeltaChatSettings(Settings):
    delta_chat_accounts: list[DeltaChatAccountConfig] = Field(default_factory=list)
    enable_native_deltachat_channel: bool = False
    deltachat_rpc_server_path: str = "deltachat-rpc-server"
    deltachat_accounts_dir: str = "/data/deltachat"
    deltachat_attachment_download_timeout_seconds: float = 30.0
    channel_upload_max_mb: int = 20
    chatwoot_upload_max_mb: int = 40
