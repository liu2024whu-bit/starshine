from __future__ import annotations

from collections.abc import Callable

from pyproj import CRS, Transformer
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
    transformer = Transformer.from_crs(source, target, always_xy=True)
    return lambda geometry: transform(transformer.transform, geometry)
