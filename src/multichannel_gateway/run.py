import asyncio

import uvicorn

from src.multichannel_gateway.app.utils import wait_until_database_ready
from src.multichannel_gateway.app.wiring import settings, pgmq, registry


async def prepare_app() -> None:
    prefork_tasks = asyncio.create_task(registry.on_prefork())
    ensure_db_task = asyncio.create_task(wait_until_database_ready(pgmq))
    await asyncio.gather(prefork_tasks, ensure_db_task)


def run() -> None:
    asyncio.run(prepare_app())
    uvicorn.run(
        "src.multichannel_gateway.app.app:app",
        host="0.0.0.0",
        port=8000,
        use_colors=True,
        loop="asyncio",
        reload=settings.environment == "LOCAL",
        workers=0 if settings.environment == "LOCAL" else settings.workers,
        log_level=settings.log_level.lower(),
    )
