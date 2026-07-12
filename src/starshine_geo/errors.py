from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkflowDiagnostic:
    """Stable, serializable details for a workflow validation failure."""

    code: str
    message: str
    path: str
    step_index: int | None = None
    operation: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation without null optional fields."""
        return {key: value for key, value in asdict(self).items() if value is not None}


class StarshineError(Exception):
    """Base error for expected workflow failures."""


class ValidationError(StarshineError):
    """Raised when input data or workflow parameters are invalid."""


class WorkflowValidationError(ValidationError):
    """Raised when a workflow document fails structural validation."""

    def __init__(self, diagnostic: WorkflowDiagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)


class UnsupportedOperationError(WorkflowValidationError):
    """Raised when a workflow requests an unregistered operation."""
