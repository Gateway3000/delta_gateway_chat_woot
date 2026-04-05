import asyncpg
import structlog

from src.multichannel_gateway.core.exceptions import TransientError

logger = structlog.get_logger(__name__)


def is_transient_postgres_error(exc: Exception) -> bool:
    return isinstance(
        exc,
        (
            OSError,
            ConnectionError,
            TimeoutError,
            asyncpg.PostgresConnectionError,
            asyncpg.CannotConnectNowError,
            asyncpg.InterfaceError,
        ),
    )


def raise_transient_postgres_error(
    exc: Exception,
    *,
    operation: str,
    queue_name: str | None = None,
    msg_id: int | None = None,
    key: str | None = None,
) -> None:
    logger.error(
        "Postgres temporarily unavailable",
        operation=operation,
        queue=queue_name,
        msg_id=msg_id,
        key=key,
        error=repr(exc),
    )
    raise TransientError(
        f"Postgres temporarily unavailable during '{operation}': {exc}",
    ) from exc
