import os
from typing import Iterator

import pytest
from _pytest.monkeypatch import MonkeyPatch
from pydantic import ValidationError

from src.multichannel_gateway.app.config import Environment, Settings


class TestValidateEnvironment:
    @staticmethod
    @pytest.fixture(autouse=True)
    def nuke_env(monkeypatch: MonkeyPatch) -> Iterator[None]:
        """
        Cleanup all env at each test begin
        """

        for key in list(os.environ):
            monkeypatch.delenv(key, raising=False)
        yield

    @staticmethod
    @pytest.mark.parametrize(
        "value, expected",
        [
            ("DEV", Environment.DEV),
            ("STAGE", Environment.STAGE),
            ("LOCAL", Environment.LOCAL),
            ("PROD", Environment.PROD),
        ],
    )
    def test_validate_environment_valid_string(
        value: str, expected: Environment, monkeypatch: MonkeyPatch
    ) -> None:
        # Test setting all available environment types to os env/.env file

        monkeypatch.setenv("environment", value)
        settings = Settings()
        assert settings.environment == expected
        assert settings.environment == value

    @staticmethod
    @pytest.mark.parametrize(
        "value",
        [
            "dev",
            "production",
            "TEST",
            "",
        ],
    )
    def test_validate_environment_invalid_value(
        value: str, monkeypatch: MonkeyPatch
    ) -> None:
        # Check getting exception when not available environment type set to os env/.env file

        monkeypatch.setenv("environment", value)
        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_message = str(exc_info.value)
        assert "1 validation error for Settings" in error_message

    @staticmethod
    def test_validate_environment_default_value() -> None:
        # Check if no value set to os env/.env file. It must be taken from config defaults

        settings = Settings()
        assert settings.environment == Environment.LOCAL
        assert settings.environment == "LOCAL"
