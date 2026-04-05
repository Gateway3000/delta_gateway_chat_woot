import asyncio

import structlog

from src.multichannel_gateway.core.exceptions import TransientError
from src.multichannel_gateway.infrastructure import PGMessageQueue

logger = structlog.get_logger(__name__)


async def wait_until_database_ready(pgmq: PGMessageQueue) -> None:
    attempt = 1
    while True:
        try:
            logger.debug(
                "Checking Postgres availability during startup", attempt=attempt
            )
            await pgmq.ensure_database_ready()
            logger.debug("Postgres is available, startup can continue", attempt=attempt)
            return
        except TransientError as exc:
            if attempt >= exc.max_transient_attempts:
                logger.critical(
                    "Postgres is unavailable during startup, retry limit exceeded",
                    attempt=attempt,
                    max_attempts=exc.max_transient_attempts,
                    error=repr(exc),
                )
                raise
            logger.error(
                "Postgres is unavailable during startup, retrying",
                attempt=attempt,
                retry_in_seconds=exc.retry_delay_seconds,
                error=repr(exc),
            )
            attempt += 1
            await asyncio.sleep(exc.retry_delay_seconds)
