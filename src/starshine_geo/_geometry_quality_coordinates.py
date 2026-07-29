from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity


@dataclass(frozen=True, slots=True)
class CoordinateStats:
    coordinate_count: int
    dimensions: frozenset[int]
    malformed: bool
    non_finite: bool

    @property
    def dimension_label(self) -> str:
        if not self.dimensions:
            return "unknown"
        if any(dimension not in {2, 3} for dimension in self.dimensions):
            return "unsupported"
        if self.dimensions == {2}:
            return "2D"
        if self.dimensions == {3}:
            return "3D"
        return "mixed"


def _merge_coordinate_stats(values: list[CoordinateStats]) -> CoordinateStats:
    return CoordinateStats(
        coordinate_count=sum(value.coordinate_count for value in values),
        dimensions=frozenset().union(*(value.dimensions for value in values)),
        malformed=any(value.malformed for value in values),
        non_finite=any(value.non_finite for value in values),
    )


def _coordinate_stats(value: Any) -> CoordinateStats:
    if not isinstance(value, (list, tuple)):
        return CoordinateStats(0, frozenset(), True, False)
    if not value:
        return CoordinateStats(0, frozenset(), False, False)

    if not isinstance(value[0], (list, tuple)):
        dimension = len(value)
        malformed = dimension < 2
        non_finite = False
        for ordinate in value:
            if isinstance(ordinate, bool) or not isinstance(ordinate, (int, float)):
                malformed = True
            elif not math.isfinite(float(ordinate)):
                non_finite = True
        return CoordinateStats(1, frozenset({dimension}), malformed, non_finite)

    return _merge_coordinate_stats([_coordinate_stats(item) for item in value])


def geometry_coordinate_stats(geometry_value: dict[str, Any]) -> CoordinateStats:
    if geometry_value.get("type") == "GeometryCollection":
        geometries = geometry_value.get("geometries")
        if not isinstance(geometries, list):
            return CoordinateStats(0, frozenset(), True, False)
        values = []
        for geometry in geometries:
            if not isinstance(geometry, dict):
                values.append(CoordinateStats(0, frozenset(), True, False))
            else:
                values.append(geometry_coordinate_stats(geometry))
        return _merge_coordinate_stats(values)
    return _coordinate_stats(geometry_value.get("coordinates"))


def safe_validity_reason(geometry: BaseGeometry) -> str:
    reason = explain_validity(geometry).split("[", 1)[0].strip()
    return reason or "Invalid geometry"


__all__ = ["CoordinateStats", "geometry_coordinate_stats", "safe_validity_reason"]
