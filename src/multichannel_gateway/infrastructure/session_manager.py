import aiohttp


class HTTPSessionManager:
    """Responsible for creating and reusing sessions across the application."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("HTTP session not initialized")
        return self._session

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()

    async def stop(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
