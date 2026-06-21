import os
from typing import Iterator

import pytest
from _pytest.monkeypatch import MonkeyPatch

from channels.imessage_channel.plugin_settings import IMessageSettings


class TestIMessageSettings:
    @staticmethod
    @pytest.fixture(autouse=True)
    def nuke_env(monkeypatch: MonkeyPatch) -> Iterator[None]:
        for key in list(os.environ):
            monkeypatch.delenv(key, raising=False)
        yield

    @staticmethod
    def test_bots_config_uses_imessage_specific_env(
        monkeypatch: MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(
            "BOTS_CONFIG",
            '[{"connector_id":"tg1","bot_token":"123:token",'
            '"cw_account_id":"777","cw_inbox_id":"888"}]',
        )
        monkeypatch.setenv(
            "IMESSAGE_BOTS_CONFIG",
            '[{"connector_id":"im1","server_url":"https://bluebubbles.local",'
            '"server_password":"secret","cw_account_id":"777",'
            '"cw_inbox_id":"999"}]',
        )

        settings = IMessageSettings()

        assert len(settings.bots_config) == 1
        assert settings.bots_config[0].connector_id == "im1"
        assert settings.bots_config[0].server_url == "https://bluebubbles.local"
