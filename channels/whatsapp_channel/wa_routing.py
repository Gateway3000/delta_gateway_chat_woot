from channels.whatsapp_channel.plugin_settings import WhatsAppConnector


class WhatsAppRouting:
    """Maps connector_id <-> cw account/inbox and the sidecar URL to call."""

    def __init__(self, config: list[WhatsAppConnector]) -> None:
        self._by_connector: dict[str, WhatsAppConnector] = {}
        self._connector_by_inbox: dict[str, str] = {}
        for c in config:
            self._by_connector[c.connector_id] = c
            self._connector_by_inbox[c.cw_inbox_id] = c.connector_id

    def get_route_by_connector_id(self, connector_id: str) -> dict[str, str]:
        c = self._by_connector.get(connector_id)
        if c is None:
            raise ValueError(f"Invalid connector_id: {connector_id}")
        return {
            "connector_id": c.connector_id,
            "cw_account_id": c.cw_account_id,
            "cw_inbox_id": c.cw_inbox_id,
            "sidecar_url": c.sidecar_url,
        }

    def get_route_by_inbox_id(self, inbox_id: str) -> dict[str, str]:
        connector_id = self._connector_by_inbox[inbox_id]
        return self.get_route_by_connector_id(connector_id)
