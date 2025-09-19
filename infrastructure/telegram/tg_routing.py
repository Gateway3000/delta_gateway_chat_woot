from app.config import BotConfig


class TelegramRouting:
    """Handles routing logic between Telegram connector IDs and Chatwoot account IDs.

    This class provides bidirectional mapping between `connector_id` and `cw_account_id`
    based on the bot configuration. It is used by the Gateway and related components
    to resolve message routes for inbound and outbound communication.
    """

    def __init__(self, bots_config: list[BotConfig]):
        self._cw_accounts: dict[str, str] = {}
        self._connectors: dict[str, str] = {}

        for cfg in bots_config:
            self._cw_accounts[cfg.connector_id] = cfg.cw_account_id
            self._connectors[cfg.cw_account_id] = cfg.connector_id

    def get_cw_account(self, connector_id: str) -> str:
        cw_account = self._cw_accounts.get(connector_id)
        if cw_account is None:
            raise ValueError(f"Invalid connector_id: {connector_id}")
        return cw_account

    def get_connector_id(self, cw_account_id: str) -> str:
        connector_id = self._connectors.get(cw_account_id)
        if connector_id is None:
            raise ValueError(f"Invalid cw_account_id: {cw_account_id}")
        return connector_id

    def get_route_by_connector_id(self, connector_id: str) -> dict[str, str]:
        return {
            "connector_id": connector_id,
            "cw_account_id": self.get_cw_account(connector_id),
        }

    def get_route_by_cw_account_id(self, cw_account_id: str) -> dict[str, str]:
        return {
            "connector_id": self.get_connector_id(cw_account_id),
            "cw_account_id": cw_account_id,
        }
