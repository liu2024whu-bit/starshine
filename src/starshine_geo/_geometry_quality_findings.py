from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_MAX_SAMPLE_INDEXES = 20


@dataclass(slots=True)
class _FindingBucket:
    severity: str
    code: str
    message: str
    geometry_type: str | None = None
    occurrence_count: int = 0
    feature_indexes: list[int] = field(default_factory=list)

    def add(self, feature_index: int | None = None) -> None:
        self.occurrence_count += 1
        if (
            feature_index is not None
            and feature_index not in self.feature_indexes
            and len(self.feature_indexes) < _MAX_SAMPLE_INDEXES
        ):
            self.feature_indexes.append(feature_index)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "occurrence_count": self.occurrence_count,
        }
        if self.geometry_type is not None:
            result["geometry_type"] = self.geometry_type
        if self.feature_indexes:
            result["feature_indexes"] = list(self.feature_indexes)
        return result


class FindingCollector:
    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str, str, str | None], _FindingBucket] = {}

    def add(
        self,
        *,
        severity: str,
        code: str,
        message: str,
        feature_index: int | None = None,
        geometry_type: str | None = None,
    ) -> None:
        key = (severity, code, message, geometry_type)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _FindingBucket(
                severity=severity,
                code=code,
                message=message,
                geometry_type=geometry_type,
            )
            self._buckets[key] = bucket
        bucket.add(feature_index)

    def findings(self) -> list[dict[str, Any]]:
        return [bucket.as_dict() for bucket in self._buckets.values()]


__all__ = ["FindingCollector"]
