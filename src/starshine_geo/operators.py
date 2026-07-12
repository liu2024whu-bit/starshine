from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from shapely.geometry import Point
from shapely.ops import unary_union

from .crs import geometry_transformer, require_projected_crs
from .errors import ValidationError
from .geojson import (
    FeatureCollection,
    iter_geometries,
    make_collection,
    make_feature,
    validate_feature_collection,
)


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
    "dissolve_features",
    "summarize_points_within",
    "validate_feature_collection",
]
