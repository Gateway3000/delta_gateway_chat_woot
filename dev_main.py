import asyncio

import uvicorn

from app.di import tg_webhooks

if __name__ == "__main__":
    asyncio.run(tg_webhooks.set_wh())
    uvicorn.run(
        "app.app:app",
        host="0.0.0.0",
        port=8000,
        use_colors=True,
        loop="asyncio",
        reload=True,
    )
