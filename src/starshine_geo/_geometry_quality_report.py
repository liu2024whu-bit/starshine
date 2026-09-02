from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from shapely import get_num_coordinates, to_wkb
from shapely.errors import GeometryTypeError, GEOSException
from shapely.geometry import shape

from ._geometry_quality_coordinates import geometry_coordinate_stats, safe_validity_reason
from ._geometry_quality_findings import FindingCollector
from ._geometry_quality_model import (
    DIMENSION_LABELS,
    GEOMETRY_QUALITY_REPORT_VERSION,
    GeometryQualityReport,
)
from .crs import parse_crs
from .errors import ValidationError
from .geojson import FeatureCollection
from .manifest import digest_json

_GEOJSON_GEOMETRY_TYPES = frozenset(
    {
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
        "GeometryCollection",
    }
)
_SHAPE_EXCEPTIONS = (
    GEOSException,
    GeometryTypeError,
    TypeError,
    ValueError,
    KeyError,
    IndexError,
)


def _safe_geometry_type_hint(value: Any) -> str:
    if isinstance(value, str) and value in _GEOJSON_GEOMETRY_TYPES:
        return value
    return "Unknown"


def _declared_crs(collection: FeatureCollection) -> tuple[str | None, str]:
    value = collection.get("starshine:crs")
    if not isinstance(value, str) or not value.strip():
        return None, "missing"
    normalized = value.strip()
    try:
        parse_crs(normalized)
    except ValidationError:
        return None, "invalid"
    return normalized, "valid"


def build_geometry_quality_report(collection: FeatureCollection) -> GeometryQualityReport:
    """Build a read-only geometry-quality report for one GeoJSON FeatureCollection."""
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        raise ValidationError("GeoJSON must be a FeatureCollection")
    features = collection.get("features")
    if not isinstance(features, list):
        raise ValidationError("FeatureCollection.features must be a list")
    findings = FindingCollector()
    try:
        collection_digest = digest_json(collection)
        collection_digest_status = "available"
    except (TypeError, ValueError):
        collection_digest = None
        collection_digest_status = "unavailable"
        findings.add(
            severity="error",
            code="non_json_collection",
            message=(
                "The collection contains values that cannot be represented as canonical JSON; "
                "its collection digest is unavailable."
            ),
        )

    geometry_counts: Counter[str] = Counter()
    dimension_counts: Counter[str] = Counter({label: 0 for label in DIMENSION_LABELS})
    parsed_geometry_count = 0
    valid_geometry_count = 0
    invalid_feature_indexes: set[int] = set()
    total_coordinate_count = 0
    max_coordinate_count = 0
    normalized_groups: dict[bytes, list[tuple[int, str]]] = defaultdict(list)

    declared_crs, crs_status = _declared_crs(collection)
    if crs_status == "missing":
        findings.add(
            severity="warning",
            code="missing_declared_crs",
            message="The collection does not declare starshine:crs.",
        )
    elif crs_status == "invalid":
        findings.add(
            severity="warning",
            code="invalid_declared_crs",
            message="The declared starshine:crs value is not parseable.",
        )

    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            findings.add(
                severity="error",
                code="invalid_feature",
                message="A collection entry is not a GeoJSON Feature object.",
                feature_index=index,
            )
            invalid_feature_indexes.add(index)
            dimension_counts["unknown"] += 1
            continue

        geometry_value = feature.get("geometry")
        if geometry_value is None:
            findings.add(
                severity="error",
                code="missing_geometry",
                message="A GeoJSON Feature has no geometry.",
                feature_index=index,
            )
            invalid_feature_indexes.add(index)
            dimension_counts["unknown"] += 1
            continue
        if not isinstance(geometry_value, dict):
            findings.add(
                severity="error",
                code="unparseable_geometry",
                message="A geometry value is not a GeoJSON geometry object.",
                feature_index=index,
            )
            invalid_feature_indexes.add(index)
            dimension_counts["unknown"] += 1
            continue

        stats = geometry_coordinate_stats(geometry_value)
        dimension_counts[stats.dimension_label] += 1
        total_coordinate_count += stats.coordinate_count
        max_coordinate_count = max(max_coordinate_count, stats.coordinate_count)
        geometry_type_hint = _safe_geometry_type_hint(geometry_value.get("type"))

        raw_error = False
        if stats.malformed:
            findings.add(
                severity="error",
                code="invalid_coordinate",
                message="A geometry contains a malformed coordinate position or coordinate array.",
                feature_index=index,
                geometry_type=geometry_type_hint,
            )
            raw_error = True
        if stats.non_finite:
            findings.add(
                severity="error",
                code="non_finite_coordinate",
                message="A geometry contains a non-finite coordinate ordinate.",
                feature_index=index,
                geometry_type=geometry_type_hint,
            )
            raw_error = True
        if stats.dimension_label == "unsupported":
            findings.add(
                severity="error",
                code="unsupported_coordinate_dimension",
                message="A geometry uses coordinate positions other than two or three dimensions.",
                feature_index=index,
                geometry_type=geometry_type_hint,
            )
            raw_error = True
        elif stats.dimension_label == "mixed":
            findings.add(
                severity="warning",
                code="mixed_coordinate_dimensions",
                message="A geometry mixes two- and three-dimensional coordinate positions.",
                feature_index=index,
                geometry_type=geometry_type_hint,
            )

        if raw_error:
            invalid_feature_indexes.add(index)
            continue

        try:
            geometry = shape(geometry_value)
        except _SHAPE_EXCEPTIONS:
            findings.add(
                severity="error",
                code="unparseable_geometry",
                message="A geometry cannot be parsed as a supported GeoJSON geometry.",
                feature_index=index,
                geometry_type=geometry_type_hint,
            )
            invalid_feature_indexes.add(index)
            continue

        parsed_geometry_count += 1
        geometry_type = geometry.geom_type
        geometry_counts[geometry_type] += 1
        parsed_coordinate_count = int(get_num_coordinates(geometry))
        total_coordinate_count += parsed_coordinate_count - stats.coordinate_count
        max_coordinate_count = max(max_coordinate_count, parsed_coordinate_count)

        if geometry.is_empty:
            findings.add(
                severity="error",
                code="empty_geometry",
                message="A geometry is empty.",
                feature_index=index,
                geometry_type=geometry_type,
            )
            invalid_feature_indexes.add(index)
            continue
        if not geometry.is_valid:
            reason = safe_validity_reason(geometry)
            findings.add(
                severity="error",
                code="topologically_invalid_geometry",
                message=f"A geometry is topologically invalid: {reason}.",
                feature_index=index,
                geometry_type=geometry_type,
            )
            invalid_feature_indexes.add(index)
            continue

        valid_geometry_count += 1
        canonical_wkb = to_wkb(
            geometry.normalize(),
            byte_order=1,
            output_dimension=3,
            include_srid=False,
        )
        normalized_groups[canonical_wkb].append((index, geometry_type))

    duplicate_geometry_group_count = 0
    duplicate_feature_count = 0
    for group in normalized_groups.values():
        if len(group) < 2:
            continue
        duplicate_geometry_group_count += 1
        duplicate_feature_count += len(group)
        for feature_index, geometry_type in group:
            findings.add(
                severity="warning",
                code="duplicate_geometry",
                message="Multiple features share an identical normalized geometry.",
                feature_index=feature_index,
                geometry_type=geometry_type,
            )

    finding_values = findings.findings()
    error_count = sum(
        finding["occurrence_count"]
        for finding in finding_values
        if finding["severity"] == "error"
    )
    warning_count = sum(
        finding["occurrence_count"]
        for finding in finding_values
        if finding["severity"] == "warning"
    )
    report: GeometryQualityReport = {
        "schema_version": GEOMETRY_QUALITY_REPORT_VERSION,
        "collection_digest": collection_digest,
        "collection_digest_status": collection_digest_status,
        "feature_count": len(features),
        "parsed_geometry_count": parsed_geometry_count,
        "valid_geometry_count": valid_geometry_count,
        "invalid_geometry_count": len(invalid_feature_indexes),
        "geometry_counts": dict(sorted(geometry_counts.items())),
        "coordinate_dimension_counts": {
            label: dimension_counts[label] for label in DIMENSION_LABELS
        },
        "total_coordinate_count": total_coordinate_count,
        "max_coordinate_count": max_coordinate_count,
        "duplicate_geometry_group_count": duplicate_geometry_group_count,
        "duplicate_feature_count": duplicate_feature_count,
        "declared_crs": declared_crs,
        "crs_status": crs_status,
        "valid": error_count == 0,
        "error_count": error_count,
        "warning_count": warning_count,
        "findings": finding_values,
    }
    report["quality_digest"] = digest_json(report)
    return report


__all__ = ["build_geometry_quality_report"]
