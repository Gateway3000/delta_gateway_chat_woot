import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from src.multichannel_gateway.app.di import incoming_worker, outgoing_worker, registry
from src.multichannel_gateway.app.utils.asyncio_policy import check_eventloop_policy
from src.multichannel_gateway.app.utils.logger import setup_logging
from src.multichannel_gateway.routers.router import router

check_eventloop_policy()
setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    asyncio.create_task(
        incoming_worker.run(), name=f"incoming_worker_pid_{os.getpid()}"
    )
    asyncio.create_task(
        outgoing_worker.run(), name=f"outgoing_worker_pid_{os.getpid()}"
    )
    await registry.on_startup()
    yield
    await registry.on_shutdown()
    await asyncio.gather(incoming_worker.stop(), outgoing_worker.stop())


app = FastAPI(
    title="Channel Gateway API",
    docs_url="/docs",
    lifespan=lifespan,
)

app.include_router(router)
