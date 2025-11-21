import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.di import tg_gateway, dp, incoming_worker, outgoing_worker
from app.routes.telegram.handlers.basic_handlers import router as telegram_handler
from app.routes.telegram.routers.router import router
from app.utils.asyncio_policy import check_eventloop_policy
from app.utils.logger import setup_logging

check_eventloop_policy()
setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await tg_gateway.set_webhooks()
    yield
    await tg_gateway.close_bot_sessions()
    await asyncio.gather(incoming_worker.stop(), outgoing_worker.stop())


app = FastAPI(
    title="Channel Gateway API",
    docs_url="/docs",
    lifespan=lifespan,
)

app.include_router(router)

dp.include_router(telegram_handler)
