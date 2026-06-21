from channels.simplex_channel.plugin_settings import BotConfig


class SimplexRouting:
    """Maps SimpleX connector IDs to Chatwoot account/inbox IDs (and back).

    Structurally identical to the Signal/iMessage routings. The CLI `user_id`
    is carried here so the envelope factory can fingerprint the connector
    (the role a bot token / phone number plays for other channels).
    """

    def __init__(self, bots_config: list[BotConfig]):
        self._cw_accounts: dict[str, str] = {}
        self._inboxes: dict[str, str] = {}
        self._connectors: dict[str, str] = {}
        self._user_ids: dict[str, int] = {}

        for cfg in bots_config:
            self._cw_accounts[cfg.connector_id] = cfg.cw_account_id
            self._inboxes[cfg.connector_id] = cfg.cw_inbox_id
            self._connectors[cfg.cw_inbox_id] = cfg.connector_id
            self._user_ids[cfg.connector_id] = cfg.user_id

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
            "user_id": str(self._user_ids.get(connector_id)),
        }

    def get_route_by_inbox_id(self, inbox_id: str) -> dict[str, str]:
        connector_id = self._connectors[inbox_id]
        return {
            "connector_id": connector_id,
            "cw_account_id": self.get_cw_account(connector_id),
            "user_id": str(self._user_ids[connector_id]),
        }

    @property
    def connector_ids(self) -> list[str]:
        return list(self._cw_accounts.keys())
