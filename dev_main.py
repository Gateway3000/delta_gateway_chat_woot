import asyncio

import uvicorn

from app.app import app
from app.di import incoming_worker, outgoing_worker


async def serve_api() -> None:
    config = uvicorn.Config(
        app, host="0.0.0.0", port=8000, loop="asyncio", reload=True, use_colors=True
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    task_api = asyncio.create_task(serve_api())
    task_incoming_worker = asyncio.create_task(
        incoming_worker.run(), name="incoming_worker"
    )
    task_outgoing_worker = asyncio.create_task(
        outgoing_worker.run(), name="outgoing_worker"
    )
    await asyncio.gather(task_api, task_incoming_worker, task_outgoing_worker)


if __name__ == "__main__":
    asyncio.run(main(), debug=True)
