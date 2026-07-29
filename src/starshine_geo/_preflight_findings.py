from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_MAX_SAMPLE_INDEXES = 20


@dataclass(slots=True)
class _FindingBucket:
    severity: str
    code: str
    message: str
    layer: str
    step_index: int | None = None
    operation: str | None = None
    input_name: str | None = None
    field_name: str | None = None
    occurrence_count: int = 0
    feature_indexes: list[int] = field(default_factory=list)

    def add(self, feature_index: int | None = None) -> None:
        self.occurrence_count += 1
        if feature_index is not None and len(self.feature_indexes) < _MAX_SAMPLE_INDEXES:
            self.feature_indexes.append(feature_index)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "layer": self.layer,
            "occurrence_count": self.occurrence_count,
        }
        if self.step_index is not None:
            result["step_index"] = self.step_index
        if self.operation is not None:
            result["operation"] = self.operation
        if self.input_name is not None:
            result["input_name"] = self.input_name
        if self.field_name is not None:
            result["field"] = self.field_name
        if self.feature_indexes:
            result["feature_indexes"] = list(self.feature_indexes)
        return result


class _FindingCollector:
    def __init__(self) -> None:
        self._buckets: dict[tuple[Any, ...], _FindingBucket] = {}

    def add(
        self,
        *,
        severity: str,
        code: str,
        message: str,
        layer: str,
        step_index: int | None = None,
        operation: str | None = None,
        input_name: str | None = None,
        field_name: str | None = None,
        feature_index: int | None = None,
    ) -> None:
        key = (
            severity,
            code,
            message,
            layer,
            step_index,
            operation,
            input_name,
            field_name,
        )
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _FindingBucket(
                severity=severity,
                code=code,
                message=message,
                layer=layer,
                step_index=step_index,
                operation=operation,
                input_name=input_name,
                field_name=field_name,
            )
            self._buckets[key] = bucket
        bucket.add(feature_index)

    def findings(self) -> list[dict[str, Any]]:
        return [bucket.as_dict() for bucket in self._buckets.values()]


__all__ = ["_FindingCollector"]
