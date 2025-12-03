import asyncio

import uvicorn

from app.di import pgmq, settings, registry


async def prepare_app() -> None:
    prefork_tasks = asyncio.create_task(registry.on_prefork())
    ensure_db_task = asyncio.create_task(pgmq.ensure_database_ready())
    await asyncio.gather(prefork_tasks, ensure_db_task)


if __name__ == "__main__":
    asyncio.run(prepare_app())
    uvicorn.run(
        "app.app:app",
        host="0.0.0.0",
        port=8000,
        use_colors=True,
        loop="asyncio",
        workers=settings.workers,
    )
