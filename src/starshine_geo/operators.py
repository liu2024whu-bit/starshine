from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from shapely.errors import GEOSException
from shapely.geometry import Point
from shapely.ops import unary_union

from ._spatial_index import DeterministicSpatialIndex
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


def _json_scalar_key(
    value: Any,
    *,
    index: int,
    field: str,
    entity: str,
) -> tuple[str, Any]:
    if value is None or isinstance(value, (dict, list)):
        raise ValidationError(
            f"{entity} {index} property {field!r} must be a non-null JSON scalar"
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise ValidationError(
            f"{entity} {index} property {field!r} must be a finite JSON scalar"
        )
    if not isinstance(value, (str, int, float, bool)):
        raise ValidationError(
            f"{entity} {index} property {field!r} must be a JSON scalar"
        )
    return type(value).__name__, value


def _raise_duplicate_identifier(
    *,
    identifier_label: str,
    entity: str,
    index: int,
    field: str,
) -> None:
    raise ValidationError(
        f"duplicate {identifier_label} identifier: "
        f"{entity} {index} property {field!r} must be unique"
    )


def _candidate_identifier_key(value: Any, *, index: int, field: str) -> tuple[str, Any]:
    return _json_scalar_key(
        value,
        index=index,
        field=field,
        entity="candidate",
    )


def _validate_json_scalar_or_null(value: Any, *, label: str) -> None:
    if value is None:
        return
    if isinstance(value, (dict, list)) or not isinstance(value, (str, int, float, bool)):
        raise ValidationError(f"{label} must be a finite JSON scalar or null")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValidationError(f"{label} must be a finite JSON scalar or null")


def _prepare_polygon_mask(
    mask: FeatureCollection,
    *,
    operation: str,
) -> tuple[Any, Any | None]:
    validated_mask = validate_feature_collection(mask)
    _, mask_crs = _required_declared_crs(validated_mask, label="mask")
    mask_geometries = []
    for _, geometry in iter_geometries(validated_mask):
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValidationError(
                f"{operation} mask must contain Polygon or MultiPolygon geometry only"
            )
        mask_geometries.append(geometry)
    if not mask_geometries:
        return mask_crs, None
    try:
        return mask_crs, unary_union(mask_geometries)
    except GEOSException as exc:
        raise ValidationError(f"{operation} mask union failed") from exc


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
    """Clip input geometries by a polygon mask in the same declared CRS."""
    validated_input = validate_feature_collection(collection)
    input_crs_label, input_crs = _required_declared_crs(validated_input, label="input")
    mask_crs, mask_union = _prepare_polygon_mask(mask, operation="clip")
    if not input_crs.equals(mask_crs):
        raise ValidationError("clip input and mask must declare equivalent CRS values")
    if mask_union is None:
        return make_collection([], crs=input_crs_label)

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


def difference_features(
    collection: FeatureCollection,
    mask: FeatureCollection,
) -> FeatureCollection:
    """Keep the portion of each input geometry outside an equivalent-CRS polygon mask."""
    validated_input = validate_feature_collection(collection)
    input_crs_label, input_crs = _required_declared_crs(validated_input, label="input")
    mask_crs, mask_union = _prepare_polygon_mask(mask, operation="difference")
    if not input_crs.equals(mask_crs):
        raise ValidationError("difference input and mask must declare equivalent CRS values")

    output = []
    for index, (feature, geometry) in enumerate(iter_geometries(validated_input)):
        if mask_union is None:
            difference = geometry
        else:
            try:
                difference = geometry.difference(mask_union)
            except GEOSException as exc:
                raise ValidationError(f"difference failed for input feature {index}") from exc
        if difference.is_empty:
            continue
        output.append(make_feature(difference, feature.get("properties")))

    return validate_feature_collection(make_collection(output, crs=input_crs_label))


def intersect_features(
    left: FeatureCollection,
    right: FeatureCollection,
    *,
    right_id_field: str,
    output_field: str = "intersection_id",
) -> FeatureCollection:
    """Emit one normalized non-empty geometry intersection for each left/right pair.

    Both inputs must declare equivalent CRS values. Candidate discovery uses a deterministic
    spatial-index wrapper, while exact intersections are emitted in ``(left_index, right_index)``
    order. Left properties are copied and the matched right identifier is appended under
    ``output_field``. Lower-dimensional boundary intersections are retained.
    """
    for label, value in {
        "right_id_field": right_id_field,
        "output_field": output_field,
    }.items():
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{label} must be a non-empty string")

    validated_left = validate_feature_collection(left)
    validated_right = validate_feature_collection(right)
    left_crs_label, left_crs = _required_declared_crs(validated_left, label="left")
    _, right_crs = _required_declared_crs(validated_right, label="right")
    if not left_crs.equals(right_crs):
        raise ValidationError("intersection inputs must declare equivalent CRS values")

    right_records: list[tuple[Any, Any]] = []
    seen_identifiers: set[tuple[str, Any]] = set()
    for right_index, (feature, geometry) in enumerate(iter_geometries(validated_right)):
        properties = feature.get("properties") or {}
        if right_id_field not in properties:
            raise ValidationError(
                f"right feature {right_index} is missing required property: {right_id_field}"
            )
        identifier = properties[right_id_field]
        key = _json_scalar_key(
            identifier,
            index=right_index,
            field=right_id_field,
            entity="right feature",
        )
        if key in seen_identifiers:
            _raise_duplicate_identifier(
                identifier_label="right",
                entity="right feature",
                index=right_index,
                field=right_id_field,
            )
        seen_identifiers.add(key)
        right_records.append((identifier, geometry))

    left_records = list(iter_geometries(validated_left))
    for left_index, (feature, _) in enumerate(left_records):
        properties = feature.get("properties") or {}
        if output_field in properties:
            raise ValidationError(
                f"left feature {left_index} already contains output property: {output_field}"
            )

    spatial_index = DeterministicSpatialIndex(
        geometry for _, geometry in right_records
    )
    output = []
    for left_index, (feature, left_geometry) in enumerate(left_records):
        right_indices = spatial_index.intersecting_indices(
            left_geometry, source_index=left_index
        )
        for right_index in right_indices:
            right_identifier, right_geometry = right_records[right_index]
            try:
                intersection = left_geometry.intersection(right_geometry)
                if intersection.is_empty:
                    continue
                intersection = intersection.normalize()
            except GEOSException as exc:
                raise ValidationError(
                    "intersection failed for left feature "
                    f"{left_index} and right feature {right_index}"
                ) from exc

            properties = dict(feature.get("properties") or {})
            properties[output_field] = right_identifier
            output.append(make_feature(intersection, properties))

    return validate_feature_collection(make_collection(output, crs=left_crs_label))


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
            _raise_duplicate_identifier(
                identifier_label="candidate",
                entity="candidate",
                index=index,
                field=candidate_id_field,
            )
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

    spatial_index = DeterministicSpatialIndex(
        geometry for _, geometry in candidate_records
    )
    output = []
    for source_index, (feature, geometry) in enumerate(source_records):
        match = spatial_index.nearest_first(
            geometry,
            source_index=source_index,
            max_distance=max_distance,
        )
        properties = dict(feature.get("properties") or {})
        if match is None:
            properties[nearest_id_field] = None
            properties[distance_field] = None
        else:
            candidate_index, nearest_distance = match
            properties[nearest_id_field] = candidate_records[candidate_index][0]
            properties[distance_field] = nearest_distance
        output.append(make_feature(geometry, properties))

    return validate_feature_collection(make_collection(output, crs=source_crs_label))


def join_points_to_polygons(
    points: FeatureCollection,
    polygons: FeatureCollection,
    *,
    polygon_id_field: str,
    output_field: str = "polygon_id",
    unmatched_value: Any = None,
    multiple_match: str = "error",
) -> FeatureCollection:
    """Attach one covering polygon identifier to every point feature.

    Polygon ``covers`` semantics include boundary points. Ambiguous multiple matches fail by
    default; the explicit ``first`` policy chooses the first covering polygon in input order.
    Unmatched points are retained with the configured JSON-scalar value.
    """
    field_values = {
        "polygon_id_field": polygon_id_field,
        "output_field": output_field,
    }
    for label, value in field_values.items():
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{label} must be a non-empty string")
    if not isinstance(multiple_match, str) or multiple_match not in {"error", "first"}:
        raise ValidationError("multiple_match must be 'error' or 'first'")
    _validate_json_scalar_or_null(unmatched_value, label="unmatched_value")

    validated_points = validate_feature_collection(points)
    validated_polygons = validate_feature_collection(polygons)
    points_crs_label, points_crs = _required_declared_crs(validated_points, label="points")
    _, polygons_crs = _required_declared_crs(validated_polygons, label="polygons")
    if not points_crs.equals(polygons_crs):
        raise ValidationError("point join inputs must declare equivalent CRS values")

    polygon_records: list[tuple[Any, Any]] = []
    seen_identifiers: set[tuple[str, Any]] = set()
    for index, (feature, geometry) in enumerate(iter_geometries(validated_polygons)):
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValidationError(
                "point join polygons must contain Polygon or MultiPolygon geometry only"
            )
        properties = feature.get("properties") or {}
        if polygon_id_field not in properties:
            raise ValidationError(
                f"polygon {index} is missing required property: {polygon_id_field}"
            )
        identifier = properties[polygon_id_field]
        key = _json_scalar_key(
            identifier,
            index=index,
            field=polygon_id_field,
            entity="polygon",
        )
        if key in seen_identifiers:
            _raise_duplicate_identifier(
                identifier_label="polygon",
                entity="polygon",
                index=index,
                field=polygon_id_field,
            )
        seen_identifiers.add(key)
        polygon_records.append((identifier, geometry))

    point_records = list(iter_geometries(validated_points))
    for index, (feature, geometry) in enumerate(point_records):
        if not isinstance(geometry, Point):
            raise ValidationError("point join source must contain Point geometry only")
        properties = feature.get("properties") or {}
        if output_field in properties:
            raise ValidationError(
                f"point feature {index} already contains output property: {output_field}"
            )

    spatial_index = DeterministicSpatialIndex(
        geometry for _, geometry in polygon_records
    )
    output = []
    for point_index, (feature, point) in enumerate(point_records):
        matches = spatial_index.covering_indices(point, point_index=point_index)
        if multiple_match == "error" and len(matches) > 1:
            raise ValidationError(f"point feature {point_index} matches multiple polygons")

        matched_identifier: Any = unmatched_value
        if matches:
            matched_identifier = polygon_records[matches[0]][0]

        properties = dict(feature.get("properties") or {})
        properties[output_field] = matched_identifier
        output.append(make_feature(point, properties))

    return validate_feature_collection(make_collection(output, crs=points_crs_label))


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
    for index, (feature, polygon) in enumerate(iter_geometries(polygons)):
        properties = dict(feature.get("properties") or {})
        polygon_id = properties.get(polygon_id_field)
        if polygon_id is None:
            raise ValidationError(f"polygon is missing required property: {polygon_id_field}")
        if polygon_id in seen_ids:
            _raise_duplicate_identifier(
                identifier_label="polygon",
                entity="polygon",
                index=index,
                field=polygon_id_field,
            )
        seen_ids.add(polygon_id)
        properties[count_field] = sum(1 for point in point_geometries if polygon.covers(point))
        output.append(make_feature(polygon, properties))
    return make_collection(output, crs=polygons.get("starshine:crs"))


__all__ = [
    "buffer_features",
    "clip_features",
    "difference_features",
    "dissolve_features",
    "intersect_features",
    "join_points_to_polygons",
    "nearest_features",
    "reproject_features",
    "summarize_points_within",
    "validate_feature_collection",
]
