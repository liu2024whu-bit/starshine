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


def _candidate_identifier_key(value: Any, *, index: int, field: str) -> tuple[str, Any]:
    if value is None or isinstance(value, (dict, list)):
        raise ValidationError(
            f"candidate {index} property {field!r} must be a non-null JSON scalar"
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise ValidationError(
            f"candidate {index} property {field!r} must be a finite JSON scalar"
        )
    if not isinstance(value, (str, int, float, bool)):
        raise ValidationError(
            f"candidate {index} property {field!r} must be a JSON scalar"
        )
    return type(value).__name__, value


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


def nearest_features(
    source: FeatureCollection,
    candidates: FeatureCollection,
    *,
    candidate_id_field: str,
    distance_field: str = "nearest_distance",
    nearest_id_field: str = "nearest_id",
    max_distance: float | None = None,
) -> FeatureCollection:
    """Attach the nearest candidate identifier and projected distance to every source feature.

    Both collections must declare equivalent projected CRS values. Candidate ties are resolved by
    input order because a later candidate replaces the current match only when its distance is
    strictly smaller. Empty candidate collections and candidates beyond ``max_distance`` produce
    explicit ``null`` output fields rather than dropping source features.
    """
    field_values = {
        "candidate_id_field": candidate_id_field,
        "distance_field": distance_field,
        "nearest_id_field": nearest_id_field,
    }
    for label, value in field_values.items():
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{label} must be a non-empty string")
    if distance_field == nearest_id_field:
        raise ValidationError("distance_field and nearest_id_field must be different")
    if max_distance is not None:
        if isinstance(max_distance, bool) or not isinstance(max_distance, (int, float)):
            raise ValidationError("max_distance must be a non-negative finite number or null")
        if not math.isfinite(float(max_distance)) or float(max_distance) < 0:
            raise ValidationError("max_distance must be a non-negative finite number or null")
        max_distance = float(max_distance)

    validated_source = validate_feature_collection(source)
    validated_candidates = validate_feature_collection(candidates)
    source_crs_label, source_crs = _required_declared_crs(validated_source, label="source")
    candidate_crs_label, candidate_crs = _required_declared_crs(
        validated_candidates, label="candidates"
    )
    if not source_crs.equals(candidate_crs):
        raise ValidationError("nearest source and candidates must declare equivalent CRS values")
    require_projected_crs(source_crs_label)
    require_projected_crs(candidate_crs_label)

    candidate_records: list[tuple[Any, Any]] = []
    seen_identifiers: set[tuple[str, Any]] = set()
    for index, (feature, geometry) in enumerate(iter_geometries(validated_candidates)):
        properties = feature.get("properties") or {}
        if candidate_id_field not in properties:
            raise ValidationError(
                f"candidate {index} is missing required property: {candidate_id_field}"
            )
        identifier = properties[candidate_id_field]
        key = _candidate_identifier_key(
            identifier, index=index, field=candidate_id_field
        )
        if key in seen_identifiers:
            raise ValidationError(f"duplicate candidate identifier: {identifier!r}")
        seen_identifiers.add(key)
        candidate_records.append((identifier, geometry))

    source_records = list(iter_geometries(validated_source))
    for index, (feature, _) in enumerate(source_records):
        properties = feature.get("properties") or {}
        for field in (nearest_id_field, distance_field):
            if field in properties:
                raise ValidationError(
                    f"source feature {index} already contains output property: {field}"
                )

    output = []
    for source_index, (feature, geometry) in enumerate(source_records):
        nearest_identifier: Any = None
        nearest_distance: float | None = None
        for candidate_index, (identifier, candidate_geometry) in enumerate(candidate_records):
            try:
                distance = float(geometry.distance(candidate_geometry))
            except GEOSException as exc:
                raise ValidationError(
                    "nearest distance failed for source feature "
                    f"{source_index} and candidate {candidate_index}"
                ) from exc
            if not math.isfinite(distance):
                raise ValidationError(
                    "nearest distance is not finite for source feature "
                    f"{source_index} and candidate {candidate_index}"
                )
            if nearest_distance is None or distance < nearest_distance:
                nearest_distance = distance
                nearest_identifier = identifier

        properties = dict(feature.get("properties") or {})
        if nearest_distance is None or (
            max_distance is not None and nearest_distance > max_distance
        ):
            properties[nearest_id_field] = None
            properties[distance_field] = None
        else:
            properties[nearest_id_field] = nearest_identifier
            properties[distance_field] = nearest_distance
        output.append(make_feature(geometry, properties))

    return validate_feature_collection(make_collection(output, crs=source_crs_label))


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
    "nearest_features",
    "reproject_features",
    "summarize_points_within",
    "validate_feature_collection",
]
