from channels.delta_chat_channel.dc_models import DeltaChatAccountConfig
from src import ConnectorNotFoundError


class DeltaChatRouting:
    def __init__(self, configs: list[DeltaChatAccountConfig]) -> None:
        self._by_connector_id: dict[str, DeltaChatAccountConfig] = {
            cfg.connector_id: cfg for cfg in configs
        }
        self._by_account_id: dict[str, str] = {}

    def get_default_connector_id(self) -> str:
        if not self._by_connector_id:
            raise ConnectorNotFoundError("No delta_chat connectors configured")
        return next(iter(self._by_connector_id))

    def register_account_id(self, connector_id: str, account_id: int) -> None:
        self._by_account_id[str(account_id)] = connector_id

    def get_connector_id_by_account_id(self, account_id: int | str) -> str:
        connector_id = self._by_account_id.get(str(account_id))
        if connector_id is None:
            raise ConnectorNotFoundError(f"Unknown account_id={account_id}")
        return connector_id

    def get_route_by_connector_id(self, connector_id: str) -> dict[str, str]:
        cfg = self._by_connector_id.get(connector_id)
        if cfg is None:
            raise ConnectorNotFoundError(f"Unknown connector_id={connector_id}")
        return {
            "connector_id": cfg.connector_id,
            "address": cfg.address,
            "password": cfg.password,
            "display_name": cfg.display_name or "",
            "avatar_path": cfg.avatar_path or "",
            "bridge_url": cfg.bridge_url or "",
            "cw_account_id": cfg.cw_account_id,
            "cw_inbox_id": cfg.cw_inbox_id,
            "storage_dir": cfg.storage_dir or "",
        }

    def get_route_by_inbox_id(self, inbox_id: str) -> dict[str, str]:
        for connector_id, cfg in self._by_connector_id.items():
            if cfg.cw_inbox_id == inbox_id:
                return self.get_route_by_connector_id(connector_id)
        raise ConnectorNotFoundError(f"Unknown cw_inbox_id={inbox_id}")

