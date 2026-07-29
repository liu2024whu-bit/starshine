from __future__ import annotations

from ._geometry_quality_model import (
    GEOMETRY_QUALITY_REPORT_VERSION,
    GeometryQualityReport,
)
from ._geometry_quality_render import render_geometry_quality_report
from ._geometry_quality_report import build_geometry_quality_report
from .geojson import FeatureCollection


def assess_geometry_quality(collection: FeatureCollection) -> GeometryQualityReport:
    """Assess GeoJSON geometry quality without repairing or transforming the collection.

    The report is coordinate- and property-value free. It records only aggregate counts, bounded
    feature-index samples, coordinate-free validity reasons, CRS metadata status, and deterministic
    collection/report digests.
    """
    return build_geometry_quality_report(collection)


def render_geometry_quality_markdown(report: GeometryQualityReport) -> str:
    """Render a deterministic Markdown geometry-quality report."""
    return render_geometry_quality_report(report)


__all__ = [
    "GEOMETRY_QUALITY_REPORT_VERSION",
    "GeometryQualityReport",
    "assess_geometry_quality",
    "render_geometry_quality_markdown",
]
