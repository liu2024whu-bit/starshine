from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from shapely.errors import GEOSException
from shapely.geometry import Point
from shapely.ops import unary_union

from .crs import geometry_transformer, parse_crs, require_projected_crs
from .errors import ValidationError
from .geojson import (
    FeatureCollection,
    iter_geometries,
    make_collection,
    make_feature,
    validate_feature_collection,
)


def _required_declared_crs(
    collection: FeatureCollection,
    *,
    label: str,
) -> tuple[str, Any]:
    value = collection.get("starshine:crs")
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} collection must declare starshine:crs")
    normalized = value.strip()
    return normalized, parse_crs(normalized)


def buffer_features(
    collection: FeatureCollection,
    *,
    distance: float,
    source_crs: str,
    work_crs: str,
    segments: int = 16,
) -> FeatureCollection:
    """Buffer every feature in a projected working CRS and return it in the source CRS."""
    if not math.isfinite(distance) or distance <= 0:
        raise ValidationError("distance must be a positive finite number")
    if not isinstance(segments, int) or not 1 <= segments <= 64:
        raise ValidationError("segments must be an integer between 1 and 64")
    require_projected_crs(work_crs)
    to_work = geometry_transformer(source_crs, work_crs)
    to_source = geometry_transformer(work_crs, source_crs)

    output = []
    for feature, geometry in iter_geometries(collection):
        buffered = to_source(to_work(geometry).buffer(distance, quad_segs=segments))
        properties = dict(feature.get("properties") or {})
        properties["starshine:buffer_distance"] = distance
        properties["starshine:work_crs"] = work_crs
        output.append(make_feature(buffered, properties))
    return make_collection(output, crs=source_crs)


def clip_features(
    collection: FeatureCollection,
    mask: FeatureCollection,
) -> FeatureCollection:
    """Clip input geometries by a polygon mask in the same declared CRS.

    The union of all mask polygons is intersected with each input feature. Empty intersections are
    omitted, while retained features keep their input order and property objects. Boundary-only
    intersections are retained because they are valid non-empty geometric results.
    """
    validated_input = validate_feature_collection(collection)
    validated_mask = validate_feature_collection(mask)

    input_crs_label, input_crs = _required_declared_crs(
        validated_input,
        label="input",
    )
    _, mask_crs = _required_declared_crs(validated_mask, label="mask")
    if not input_crs.equals(mask_crs):
        raise ValidationError("clip input and mask must declare equivalent CRS values")

    mask_geometries = []
    for _, geometry in iter_geometries(validated_mask):
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValidationError("clip mask must contain Polygon or MultiPolygon geometry only")
        mask_geometries.append(geometry)

    if not mask_geometries:
        return make_collection([], crs=input_crs_label)

    try:
        mask_union = unary_union(mask_geometries)
    except GEOSException as exc:
        raise ValidationError("clip mask union failed") from exc

    output = []
    for index, (feature, geometry) in enumerate(iter_geometries(validated_input)):
        try:
            clipped = geometry.intersection(mask_union)
        except GEOSException as exc:
            raise ValidationError(f"clip failed for input feature {index}") from exc
        if clipped.is_empty:
            continue
        output.append(make_feature(clipped, feature.get("properties")))

    return validate_feature_collection(make_collection(output, crs=input_crs_label))


def reproject_features(
    collection: FeatureCollection,
    *,
    target_crs: str,
    source_crs: str | None = None,
) -> FeatureCollection:
    """Transform every geometry to ``target_crs`` while preserving feature properties and order."""
    validated = validate_feature_collection(collection)
    declared_value = validated.get("starshine:crs")
    declared_crs = (
        declared_value.strip()
        if isinstance(declared_value, str) and declared_value.strip()
        else None
    )

    if source_crs is None:
        if declared_crs is None:
            raise ValidationError(
                "source_crs is required when the collection has no starshine:crs"
            )
        resolved_source = declared_crs
    else:
        if not isinstance(source_crs, str) or not source_crs.strip():
            raise ValidationError("source_crs must be a non-empty string when provided")
        resolved_source = source_crs.strip()
        if declared_crs is not None:
            supplied = parse_crs(resolved_source)
            declared = parse_crs(declared_crs)
            if not supplied.equals(declared):
                raise ValidationError(
                    "source_crs does not match the collection starshine:crs"
                )

    if not isinstance(target_crs, str) or not target_crs.strip():
        raise ValidationError("target_crs must be a non-empty string")

    source = parse_crs(resolved_source)
    target = parse_crs(target_crs.strip())
    transform_geometry = geometry_transformer(source.to_string(), target.to_string())

    output = []
    for feature, geometry in iter_geometries(validated):
        properties = dict(feature.get("properties") or {})
        output.append(make_feature(transform_geometry(geometry), properties))

    result = make_collection(output, crs=target.to_string())
    return validate_feature_collection(result)


def dissolve_features(
    collection: FeatureCollection,
    *,
    group_field: str | None = None,
) -> FeatureCollection:
    """Dissolve all geometries, optionally grouped by one property."""
    groups: dict[Any, list] = defaultdict(list)
    for feature, geometry in iter_geometries(collection):
        key = None if group_field is None else (feature.get("properties") or {}).get(group_field)
        groups[key].append(geometry)

    features = []
    for key, geometries in groups.items():
        properties = {} if group_field is None else {group_field: key}
        features.append(make_feature(unary_union(geometries), properties))
    return make_collection(features, crs=collection.get("starshine:crs"))


def summarize_points_within(
    polygons: FeatureCollection,
    points: FeatureCollection,
    *,
    polygon_id_field: str = "id",
    count_field: str = "point_count",
) -> FeatureCollection:
    """Count point features covered by each polygon, preserving polygon properties."""
    if not polygon_id_field.strip() or not count_field.strip():
        raise ValidationError("field names must not be blank")

    point_geometries = []
    for _, geometry in iter_geometries(points):
        if not isinstance(geometry, Point):
            raise ValidationError("points must contain Point geometry only")
        point_geometries.append(geometry)

    output = []
    seen_ids: set[Any] = set()
    for feature, polygon in iter_geometries(polygons):
        properties = dict(feature.get("properties") or {})
        polygon_id = properties.get(polygon_id_field)
        if polygon_id is None:
            raise ValidationError(f"polygon is missing required property: {polygon_id_field}")
        if polygon_id in seen_ids:
            raise ValidationError(f"duplicate polygon identifier: {polygon_id!r}")
        seen_ids.add(polygon_id)
        properties[count_field] = sum(1 for point in point_geometries if polygon.covers(point))
        output.append(make_feature(polygon, properties))
    return make_collection(output, crs=polygons.get("starshine:crs"))


__all__ = [
    "buffer_features",
    "clip_features",
    "dissolve_features",
    "reproject_features",
    "summarize_points_within",
    "validate_feature_collection",
]
