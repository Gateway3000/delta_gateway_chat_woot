from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.di import tg_gateway, pgmq, dp
from app.routes.telegram.handlers.basic_handlers import router as telegram_handler
from app.routes.telegram.routers.router import router as telegram_router
from app.utils.asyncio_policy import check_eventloop_policy

check_eventloop_policy()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await tg_gateway.set_webhooks()
    yield
    await tg_gateway.close_bot_sessions()
    await pgmq.close()


app = FastAPI(
    title="Channel Gateway API",
    docs_url="/docs",
    lifespan=lifespan,
)


app.include_router(telegram_router)

dp.include_router(telegram_handler)
