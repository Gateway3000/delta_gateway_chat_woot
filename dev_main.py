import asyncio

import uvicorn

from app.di import tg_webhooks, pgmq


async def main() -> None:
    set_wh_task = asyncio.create_task(tg_webhooks.set_wh())
    ensure_db_task = asyncio.create_task(pgmq.ensure_database_ready())

    await asyncio.gather(set_wh_task, ensure_db_task)

    uvicorn.run(
        "app.app:app",
        host="0.0.0.0",
        port=8000,
        use_colors=True,
        loop="asyncio",
        reload=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
