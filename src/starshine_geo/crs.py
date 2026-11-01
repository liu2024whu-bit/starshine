from __future__ import annotations

from collections.abc import Callable
from functools import partial

from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from .errors import ValidationError


def parse_crs(value: str) -> CRS:
    try:
        return CRS.from_user_input(value)
    except Exception as exc:
        raise ValidationError(f"Invalid CRS: {value}") from exc


def require_projected_crs(value: str) -> CRS:
    crs = parse_crs(value)
    if not crs.is_projected:
        raise ValidationError(
            f"Operation requires a projected CRS with linear units, received: {value}"
        )
    return crs


def geometry_transformer(source_crs: str, target_crs: str) -> Callable[[BaseGeometry], BaseGeometry]:
    source = parse_crs(source_crs)
    target = parse_crs(target_crs)
    try:
        transformer = Transformer.from_crs(source, target, always_xy=True)
    except ProjError as exc:
        raise ValidationError("geometry coordinate transformation could not be created") from exc

    def transform_geometry(geometry: BaseGeometry) -> BaseGeometry:
        try:
            result = transform(partial(transformer.transform, errcheck=True), geometry)
        except ProjError as exc:
            raise ValidationError("geometry coordinate transformation failed") from exc
        if result.is_empty or not result.is_valid:
            raise ValidationError("geometry coordinate transformation produced invalid geometry")
        return result

    return transform_geometry
