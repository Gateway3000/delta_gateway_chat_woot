import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.di import dp, incoming_worker, outgoing_worker, registry
from app.routes.telegram.handlers.basic_handlers import router as telegram_handler
from app.routes.telegram.routers.router import router
from app.utils.asyncio_policy import check_eventloop_policy
from app.utils.logger import setup_logging

check_eventloop_policy()
setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
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

dp.include_router(telegram_handler)
