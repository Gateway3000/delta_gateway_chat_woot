import asyncio
import json

from core.interfaces.message_queue import IMessageQueue


class OutgoingWorker:
    def __init__(self, mq: IMessageQueue, queue_name: str):
        self._mq = mq
        self._queue_name = queue_name

    @staticmethod
    async def handle_message(message: str) -> None:
        from app.di import gateways

        data = json.loads(message)
        gateway = gateways.get_gateway(data["channel"])
        await gateway.send_to_user(message)

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
