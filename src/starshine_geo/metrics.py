from __future__ import annotations

import math
from typing import Any

from .crs import parse_crs, require_projected_crs
from .errors import ValidationError
from .geojson import (
    FeatureCollection,
    iter_geometries,
    make_collection,
    make_feature,
    validate_feature_collection,
)


def _required_projected_crs(collection: FeatureCollection) -> str:
    value = collection.get("starshine:crs")
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("geometry metrics input must declare starshine:crs")
    label = value.strip()
    parse_crs(label)
    require_projected_crs(label)
    return label


def calculate_geometry_metrics(
    collection: FeatureCollection,
    *,
    area_field: str = "geometry_area",
    length_field: str = "geometry_length",
) -> FeatureCollection:
    """Attach projected area and length values while preserving geometry, properties, and order.

    Polygon length includes exterior and interior ring boundaries. Point and line area values follow
    the underlying geometry model and are therefore zero. No reprojection or geometry repair occurs.
    """
    field_values = {"area_field": area_field, "length_field": length_field}
    for label, value in field_values.items():
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{label} must be a non-empty string")
    if area_field == length_field:
        raise ValidationError("area_field and length_field must be different")

    validated = validate_feature_collection(collection)
    crs_label = _required_projected_crs(validated)
    records = list(iter_geometries(validated))

    for index, (feature, _) in enumerate(records):
        properties = feature.get("properties") or {}
        for field in (area_field, length_field):
            if field in properties:
                raise ValidationError(
                    f"feature {index} already contains geometry metric property: {field}"
                )

    output = []
    for index, (feature, geometry) in enumerate(records):
        area = float(geometry.area)
        length = float(geometry.length)
        if not math.isfinite(area) or not math.isfinite(length):
            raise ValidationError(f"geometry metrics are not finite for feature {index}")
        properties: dict[str, Any] = dict(feature.get("properties") or {})
        properties[area_field] = area
        properties[length_field] = length
        output.append(make_feature(geometry, properties))

    return validate_feature_collection(make_collection(output, crs=crs_label))


__all__ = ["calculate_geometry_metrics"]
