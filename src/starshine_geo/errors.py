class StarshineError(Exception):
    """Base error for expected workflow failures."""


class ValidationError(StarshineError):
    """Raised when input data or workflow parameters are invalid."""


class UnsupportedOperationError(StarshineError):
    """Raised when a workflow requests an unregistered operation."""
