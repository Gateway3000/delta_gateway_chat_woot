from channels.email_channel.plugin_settings import MailboxConfig
from src import ConnectorNotFoundError


class EmailRouting:
    """Maps Email connector IDs and Chatwoot inbox IDs to mailbox config."""

    def __init__(self, mailboxes_config: list[MailboxConfig]) -> None:
        self._mailboxes_by_connector_id: dict[str, MailboxConfig] = {}
        self._connectors_by_inbox_id: dict[str, str] = {}

        for cfg in mailboxes_config:
            self._mailboxes_by_connector_id[cfg.connector_id] = cfg
            self._connectors_by_inbox_id[cfg.cw_inbox_id] = cfg.connector_id

    def get_route_by_connector_id(self, connector_id: str) -> dict[str, str]:
        cfg = self.get_mailbox_by_connector_id(connector_id)
        return {
            "connector_id": cfg.connector_id,
            "cw_account_id": cfg.cw_account_id,
            "cw_inbox_id": cfg.cw_inbox_id,
            "imap_mailbox": cfg.imap_mailbox,
            "smtp_from": cfg.smtp.smtp_from,
        }

    def get_route_by_inbox_id(self, inbox_id: str) -> dict[str, str]:
        connector_id = self._connectors_by_inbox_id.get(inbox_id)
        if connector_id is None:
            raise ConnectorNotFoundError(f"Unknown cw_inbox_id={inbox_id}")
        return self.get_route_by_connector_id(connector_id)

    def get_mailbox_by_connector_id(self, connector_id: str) -> MailboxConfig:
        cfg = self._mailboxes_by_connector_id.get(connector_id)
        if cfg is None:
            raise ConnectorNotFoundError(f"Unknown connector_id={connector_id}")
        return cfg
