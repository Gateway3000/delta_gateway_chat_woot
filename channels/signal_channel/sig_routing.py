from channels.signal_channel.plugin_settings import BotConfig


class SignalRouting:
    """Maps Signal connector IDs to Chatwoot account/inbox IDs (and back).

    Structurally identical to TelegramRouting / IMessageRouting. The only
    channel-specific field carried here is the registered `number`, which
    the idempotency key uses as the per-account fingerprint (the role
    Telegram's bot-token suffix plays).
    """

    def __init__(self, bots_config: list[BotConfig]):
        self._cw_accounts: dict[str, str] = {}
        self._inboxes: dict[str, str] = {}
        self._connectors: dict[str, str] = {}
        self._numbers: dict[str, str] = {}

        for cfg in bots_config:
            self._cw_accounts[cfg.connector_id] = cfg.cw_account_id
            self._inboxes[cfg.connector_id] = cfg.cw_inbox_id
            self._connectors[cfg.cw_inbox_id] = cfg.connector_id
            self._numbers[cfg.connector_id] = cfg.number

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
            "number": str(self._numbers.get(connector_id)),
        }

    def get_route_by_inbox_id(self, inbox_id: str) -> dict[str, str]:
        connector_id = self._connectors[inbox_id]
        return {
            "connector_id": connector_id,
            "cw_account_id": self.get_cw_account(connector_id),
            "number": str(self._numbers[connector_id]),
        }

    @property
    def connector_ids(self) -> list[str]:
        return list(self._cw_accounts.keys())
