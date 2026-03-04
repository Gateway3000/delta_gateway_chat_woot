from abc import ABC, abstractmethod


class IChatwootClient(ABC):
    @abstractmethod
    async def deliver_message(
        self,
        account_id: int,
        identifier: str,
        inbox_id: int,
        content: str,
        name: str | None = None,
        email: str | None = None,
        phone_number: str | None = None,
    ) -> None: ...
