import asyncio
from typing import Any

from core.interfaces.message_queue import IMessageQueue


class IncomingWorker:
    def __init__(self, mq: IMessageQueue, queue_name: str):
        self._mq = mq
        self._queue_name = queue_name

    @staticmethod
    async def handle_message(message: dict[str, Any]) -> None:
        print(f"[IncomingWorker] Processing: {message}")

    async def run(self) -> None:
        while True:
            messages = await self._mq.read(self._queue_name, vt=30, limit=1)
            if not messages:
                await asyncio.sleep(1)
                continue

            for msg in messages:
                try:
                    await self.handle_message(msg["message"])
                    await self._mq.delete(self._queue_name, msg["msg_id"])
                except Exception as e:
                    print(f"Error: {e}")
                    await self._mq.archive(self._queue_name, msg["msg_id"])
