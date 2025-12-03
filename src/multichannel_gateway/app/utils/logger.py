import logging
from typing import Any

import structlog

from src.multichannel_gateway.app.di import settings

RESET = "\x1b[0m"
COLORS = {
    "debug": "\x1b[36;1m",
    "info": "\x1b[32;1m",
    "warning": "\x1b[33;1m",
    "error": "\x1b[31;1m",
    "critical": "\x1b[31;1m",
    "timestamp": "\x1b[33m",
    "location": "\x1b[34;1m",
    "event": "\x1b[33m",
    "key": "\x1b[36m",
    "value": "\x1b[33m",
}


class CustomConsoleRenderer:
    """Custom renderer for structlog that formats logs for console output
    with colors, aligned location, event message, and key-value pairs.

    This renderer is intended for development environments to improve
    readability of logs in the console. It extracts standard fields
    (timestamp, log level, module, function, line number) and arranges them
    in a structured and colorized format.
    """

    def __call__(
        self,
        logger: structlog.BoundLogger,
        name: str,
        event_dict: dict[str, Any],
    ) -> str:
        ts = event_dict.pop("timestamp", "")
        level = event_dict.pop("level", "").upper()

        module = event_dict.pop("module", None)
        func = event_dict.pop("func_name", None)
        lineno = event_dict.pop("lineno", None)

        # Removing logger from extras
        event_dict.pop("logger", None)

        location = ""
        if module:
            if func and lineno:
                location = f"[{logger.name}.{func}:{lineno}]"
            elif func:
                location = f"[{logger.name}.{func}]"
            else:
                location = f"[{logger.name}]"

        event = event_dict.pop("event", "")

        extras_parts = [
            f"{COLORS['key']}{k}{RESET}={COLORS['value']}{v}{RESET}"
            for k, v in event_dict.items()
        ]
        extras = " ".join(extras_parts)

        return (
            f"{COLORS['timestamp']}{ts}{RESET} "
            f"{COLORS.get(level.lower(), '')}{level:^8}{RESET}"
            f"{COLORS['location']}{location:<60}{RESET} "
            f"{COLORS['event']}{event:<40}{RESET} "
            f"{extras}"
        )


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()), format="%(message)s"
    )

    logging.getLogger("asyncio").setLevel(logging.WARNING)

    if settings.environment == "DEVELOPMENT":
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.dict_tracebacks,
                structlog.processors.CallsiteParameterAdder(
                    parameters={
                        structlog.processors.CallsiteParameter.FUNC_NAME,
                        structlog.processors.CallsiteParameter.LINENO,
                        structlog.processors.CallsiteParameter.MODULE,
                    }
                ),
                CustomConsoleRenderer(),
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        # Prod: JSON logs for Grafana/Loki
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
