"""Delta Chat routing tests."""

# mypy: disable-error-code=no-untyped-def

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

    def test_same_chat_id_routes_by_connector_id(
        self, account_config: DeltaChatAccountConfig
    ) -> None:
        second_account = account_config.model_copy(
            update={
                "connector_id": "delta-client-2",
                "address": "bot2@example.org",
                "cw_account_id": "1",
                "cw_inbox_id": "6",
            }
        )
        routing = DeltaChatRouting([account_config, second_account])

        route = routing.get_route_by_connector_id(second_account.connector_id)

        assert route["connector_id"] == "delta-client-2"
        assert route["cw_inbox_id"] == "6"
