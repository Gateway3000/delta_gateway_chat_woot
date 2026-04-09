from telegram.plugin_settings import BotConfig


class TelegramRouting:
    """Handles routing logic between Telegram connector IDs and Chatwoot account IDs.

    This class provides bidirectional mapping between `connector_id` and `cw_account_id`
    based on the bot configuration. It is used by the Gateway and related components
    to resolve message routes for inbound and outbound communication.
    """

    def __init__(self, bots_config: list[BotConfig]):
        self._cw_accounts: dict[str, str] = {}
        self._inboxes: dict[str, str] = {}
        self._connectors: dict[str, str] = {}
        self._bot_tokens: dict[str, str] = {}

        for cfg in bots_config:
            self._cw_accounts[cfg.connector_id] = cfg.cw_account_id
            self._inboxes[cfg.connector_id] = cfg.cw_inbox_id
            self._connectors[cfg.cw_inbox_id] = cfg.connector_id
            self._bot_tokens[cfg.connector_id] = cfg.bot_token

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
            "bot_token": str(self._bot_tokens.get(connector_id)),
        }

    def get_route_by_inbox_id(self, inbox_id: str) -> dict[str, str]:
        return {
            "connector_id": self._connectors[inbox_id],
            "cw_account_id": self.get_cw_account(self._connectors[inbox_id]),
            "bot_token": str(self._bot_tokens[self._connectors[inbox_id]]),
        }
