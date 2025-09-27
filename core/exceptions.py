class ConnectorNotFoundError(Exception):
    """Raised when connector_id is unknown."""


class WrongUpdateTypeError(Exception):
    """Raised when inbound update has no message."""


class TransientError(Exception):
    """A temporary error that can be retried later."""

    def __init__(self, message: str = "", *, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after  # seconds


class RateLimitError(Exception):
    """A specific rate-limit error."""


class FatalError(Exception):
    """An error for which the message should be sent to the DLQ or archived."""
