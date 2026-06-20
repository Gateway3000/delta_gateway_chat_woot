from channels.delta_chat_channel.dc_models import DeltaChatAccountConfig
from channels.delta_chat_channel.dc_routing import DeltaChatRouting


class TestDeltaChatRouting:
    def test_get_route_by_connector_id(self, routing: DeltaChatRouting, account_config: DeltaChatAccountConfig) -> None:
        route = routing.get_route_by_connector_id(account_config.connector_id)

        assert route["connector_id"] == account_config.connector_id
        assert route["address"] == account_config.address
        assert route["cw_account_id"] == account_config.cw_account_id
        assert route["cw_inbox_id"] == account_config.cw_inbox_id

    def test_register_and_resolve_account_id(
        self, routing: DeltaChatRouting, account_config: DeltaChatAccountConfig
    ) -> None:
        routing.register_account_id(account_config.connector_id, 42)

        assert routing.get_connector_id_by_account_id(42) == account_config.connector_id

