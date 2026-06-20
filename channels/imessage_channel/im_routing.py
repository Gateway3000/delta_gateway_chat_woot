from channels.imessage_channel.plugin_settings import BotConfig


class IMessageRouting:
    """Handles routing logic between BlueBubbles connector IDs and Chatwoot
    account IDs.

    Structurally identical to TelegramRouting — this bookkeeping has no
    platform-specific logic in it, which is exactly why it's a strong
    candidate to be hoisted into a shared `ConnectorRouting` base in `src`
    once a second or third channel confirms the pattern holds.
    """

    def __init__(self, bots_config: list[BotConfig]):
        self._cw_accounts: dict[str, str] = {}
        self._inboxes: dict[str, str] = {}
        self._connectors: dict[str, str] = {}
        self._server_passwords: dict[str, str] = {}

        for cfg in bots_config:
            self._cw_accounts[cfg.connector_id] = cfg.cw_account_id
            self._inboxes[cfg.connector_id] = cfg.cw_inbox_id
            self._connectors[cfg.cw_inbox_id] = cfg.connector_id
            self._server_passwords[cfg.connector_id] = cfg.server_password

    def get_cw_account(self, connector_id: str) -> str:
        cw_account = self._cw_accounts.get(connector_id)
        if cw_account is None:
            raise ValueError(f"Invalid connector_id: {connector_id}")
        return cw_account

    def get_route_by_connector_id(self, connector_id: str) -> dict[str, str]:
        return {
            "connector_id": connector_id,
            "cw_account_id": self.get_cw_account(connector_id),
            "cw_inbox_id": str(self._inboxes.get(connector_id)),
            "server_password": str(self._server_passwords.get(connector_id)),
        }

    def get_route_by_inbox_id(self, inbox_id: str) -> dict[str, str]:
        connector_id = self._connectors[inbox_id]
        return {
            "connector_id": connector_id,
            "cw_account_id": self.get_cw_account(connector_id),
            "server_password": str(self._server_passwords[connector_id]),
        }
