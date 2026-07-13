from __future__ import annotations

from collections import Counter
from math import inf
from typing import Any

from shapely.geometry import shape

from .geojson import FeatureCollection, validate_feature_collection
from .manifest import digest_json

INSPECTION_REPORT_VERSION = 1
InspectionReport = dict[str, Any]


def inspect_feature_collection(collection: FeatureCollection) -> InspectionReport:
    """Validate and summarize a GeoJSON FeatureCollection without modifying it.

    The report contains only collection-level structure: counts, declared CRS, union bounds,
    property names, and a deterministic digest. Feature properties and coordinates are not copied
    into the report.
    """
    validated = validate_feature_collection(collection)
    features = validated["features"]

    geometry_counts: Counter[str] = Counter()
    property_fields: set[str] = set()
    min_x = min_y = inf
    max_x = max_y = -inf

    for feature in features:
        geometry = shape(feature["geometry"])
        geometry_counts[geometry.geom_type] += 1
        bounds = geometry.bounds
        min_x = min(min_x, bounds[0])
        min_y = min(min_y, bounds[1])
        max_x = max(max_x, bounds[2])
        max_y = max(max_y, bounds[3])

        properties = feature.get("properties") or {}
        property_fields.update(str(name) for name in properties)

    declared_crs = validated.get("starshine:crs")
    if not isinstance(declared_crs, str) or not declared_crs.strip():
        declared_crs = None

    bbox = None if not features else [min_x, min_y, max_x, max_y]
    return {
        "schema_version": INSPECTION_REPORT_VERSION,
        "collection_digest": digest_json(validated),
        "feature_count": len(features),
        "geometry_counts": dict(sorted(geometry_counts.items())),
        "property_fields": sorted(property_fields),
        "declared_crs": declared_crs,
        "bbox": bbox,
    }


__all__ = ["INSPECTION_REPORT_VERSION", "InspectionReport", "inspect_feature_collection"]
