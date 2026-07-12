from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from .errors import ValidationError

Feature = dict[str, Any]
FeatureCollection = dict[str, Any]


def validate_feature_collection(collection: FeatureCollection) -> FeatureCollection:
    if collection.get("type") != "FeatureCollection":
        raise ValidationError("GeoJSON must be a FeatureCollection")
    features = collection.get("features")
    if not isinstance(features, list):
        raise ValidationError("FeatureCollection.features must be a list")

    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValidationError(f"Feature {index} is not a GeoJSON Feature")
        geometry_value = feature.get("geometry")
        if geometry_value is None:
            raise ValidationError(f"Feature {index} has no geometry")
        try:
            geometry = shape(geometry_value)
        except Exception as exc:
            raise ValidationError(f"Feature {index} has invalid geometry: {exc}") from exc
        if geometry.is_empty:
            raise ValidationError(f"Feature {index} has empty geometry")
        if not geometry.is_valid:
            raise ValidationError(f"Feature {index} has topologically invalid geometry")
        properties = feature.get("properties", {})
        if properties is not None and not isinstance(properties, dict):
            raise ValidationError(f"Feature {index}.properties must be an object or null")
    return deepcopy(collection)


def iter_geometries(collection: FeatureCollection) -> Iterable[tuple[Feature, BaseGeometry]]:
    validated = validate_feature_collection(collection)
    for feature in validated["features"]:
        yield feature, shape(feature["geometry"])


def make_feature(geometry: BaseGeometry, properties: dict[str, Any] | None = None) -> Feature:
    return {
        "type": "Feature",
        "properties": dict(properties or {}),
        "geometry": mapping(geometry),
    }


def make_collection(features: list[Feature], *, crs: str | None = None) -> FeatureCollection:
    result: FeatureCollection = {"type": "FeatureCollection", "features": features}
    if crs:
        result["starshine:crs"] = crs
    return result
