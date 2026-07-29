from __future__ import annotations

from typing import Any

GEOMETRY_QUALITY_REPORT_VERSION = 1
GeometryQualityReport = dict[str, Any]

DIMENSION_LABELS = ("2D", "3D", "mixed", "unsupported", "unknown")

__all__ = [
    "DIMENSION_LABELS",
    "GEOMETRY_QUALITY_REPORT_VERSION",
    "GeometryQualityReport",
]
