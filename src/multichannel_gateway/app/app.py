import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from src.multichannel_gateway.app.utils import (
    check_eventloop_policy,
    log_background_task_result,
    setup_logging,
)
from src.multichannel_gateway.app.wiring import (
    cw_session_manager,
    incoming_worker,
    outgoing_worker,
    registry,
    telemetry_settings,
)
from src.multichannel_gateway.infrastructure.endpoints import router
from src.multichannel_gateway.infrastructure.telemetry import (
    setup_sentry,
    setup_tracing,
)

check_eventloop_policy()
setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await registry.on_startup()
    await cw_session_manager.start()
    incoming_task = asyncio.create_task(
        incoming_worker.run(), name=f"incoming_worker_pid_{os.getpid()}"
    )
    outgoing_task = asyncio.create_task(
        outgoing_worker.run(), name=f"outgoing_worker_pid_{os.getpid()}"
    )
    incoming_task.add_done_callback(log_background_task_result)
    outgoing_task.add_done_callback(log_background_task_result)
    yield
    await registry.on_shutdown()
    await cw_session_manager.stop()
    await asyncio.gather(incoming_worker.stop(), outgoing_worker.stop())
    await asyncio.gather(incoming_task, outgoing_task, return_exceptions=True)


app = FastAPI(
    title="Channel Gateway API",
    docs_url="/docs",
    lifespan=lifespan,
)

setup_sentry(telemetry_settings)
setup_tracing(app, telemetry_settings)
app.include_router(router)
