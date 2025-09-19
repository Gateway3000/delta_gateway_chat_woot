class ConnectorNotFoundError(Exception):
    """Raised when connector_id is unknown."""


class WrongUpdateTypeError(Exception):
    """Raised when inbound update has no message."""
