import asyncio

import structlog

logger = structlog.get_logger(__name__)


def log_background_task_result(task: asyncio.Task[None]) -> None:
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        logger.info("Background task cancelled", task_name=task.get_name())
        return

    if exc is not None:
        logger.critical(
            "Background task crashed",
            task_name=task.get_name(),
            error=repr(exc),
        )
