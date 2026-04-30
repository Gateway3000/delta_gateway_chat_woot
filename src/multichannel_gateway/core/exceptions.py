class ConnectorNotFoundError(Exception):
    """Raised when connector_id is unknown."""


class WrongUpdateTypeError(Exception):
    """Raised when Channel -> Chatwoot update has no message."""


class IdempotencyKeyAlreadyProcessedError(Exception):
    """Raised when idempotency key has already been processed."""


class TransientError(Exception):
    """A temporary error that can be retried later."""

    def __init__(
        self,
        message: str = "",
        max_transient_attempts: int = 10,
        retry_delay_seconds: int = 600,
    ):
        super().__init__(message)
        self._max_transient_attempts = max_transient_attempts
        self._retry_delay_seconds = retry_delay_seconds

    @property
    def max_transient_attempts(self) -> int:
        return self._max_transient_attempts

    @property
    def retry_delay_seconds(self) -> int:
        return self._retry_delay_seconds


class RateLimitError(Exception):
    """A specific rate-limit error."""

    DEFAULT_RETRY_AFTER_SECONDS = 5

    def __init__(
        self,
        message: str = "",
        retry_after_seconds: float = DEFAULT_RETRY_AFTER_SECONDS,
    ):
        super().__init__(message)
        self._retry_after_seconds = retry_after_seconds

    @property
    def retry_after_seconds(self) -> float:
        return self._retry_after_seconds


class FatalError(Exception):
    """An error for which the message should be sent to the DLQ or archived."""
