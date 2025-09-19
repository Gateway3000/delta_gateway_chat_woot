from abc import ABC, abstractmethod
from typing import Any


class IMessageQueue(ABC):
    @abstractmethod
    async def send(self, queue_name: str, payload: str) -> None: ...

    @abstractmethod
    async def read(
        self, queue_name: str, vt: int = 30, limit: int = 1
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def delete(self, queue_name: str, msg_id: int) -> None: ...

    @abstractmethod
    async def archive(self, queue_name: str, msg_id: int) -> None: ...

    @abstractmethod
    async def is_already_processed(self, key: str) -> bool: ...

    @abstractmethod
    async def mark_as_processed(self, key: str) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...
