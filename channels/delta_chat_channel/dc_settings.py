from pydantic import Field

from src import Settings

from .dc_models import DeltaChatAccountConfig


class DeltaChatSettings(Settings):
    delta_chat_accounts: list[DeltaChatAccountConfig] = Field(default_factory=list)
    enable_native_deltachat_channel: bool = False
    deltachat_rpc_server_path: str = "deltachat-rpc-server"
    deltachat_accounts_dir: str = "/data/deltachat"


