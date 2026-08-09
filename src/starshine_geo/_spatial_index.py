from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from shapely import STRtree
from shapely.errors import GEOSException
from shapely.geometry.base import BaseGeometry

from .errors import ValidationError


def _query_nearest(
    tree: STRtree,
    geometry: BaseGeometry,
    *,
    max_distance: float | None,
) -> tuple[Any, Any]:
    kwargs: dict[str, Any] = {
        "all_matches": True,
        "return_distance": True,
    }
    # Shapely requires a strictly positive query limit. Starshine accepts zero and applies its
    # inclusive threshold after the exact nearest distance is known.
    if max_distance is not None and max_distance > 0:
        kwargs["max_distance"] = max_distance
    return tree.query_nearest(geometry, **kwargs)


def _query_covered_by(tree: STRtree, geometry: BaseGeometry) -> Any:
    # STRtree evaluates predicate(input_geometry, tree_geometry). Point covered_by polygon is the
    # inverse orientation of the public polygon.covers(point) contract.
    return tree.query(geometry, predicate="covered_by")


def _query_intersects(tree: STRtree, geometry: BaseGeometry) -> Any:
    return tree.query(geometry, predicate="intersects")


class DeterministicSpatialIndex:
    """Immutable STRtree wrapper that preserves Starshine input-order semantics.

    STRtree query order is deliberately treated as opaque. Every result is converted back to the
    original geometry index before the public operator applies identifier or ambiguity policies.
    """

    __slots__ = ("_geometries", "_tree")

    def __init__(self, geometries: Iterable[BaseGeometry]) -> None:
        self._geometries = tuple(geometries)
        self._tree = STRtree(self._geometries) if self._geometries else None

    @property
    def size(self) -> int:
        return len(self._geometries)

    def nearest_first(
        self,
        geometry: BaseGeometry,
        *,
        source_index: int,
        max_distance: float | None,
    ) -> tuple[int, float] | None:
        """Return the nearest original index, resolving exact ties by input order."""
        if self._tree is None:
            return None

        try:
            raw_indices, raw_distances = _query_nearest(
                self._tree,
                geometry,
                max_distance=max_distance,
            )
        except GEOSException:
            return self._nearest_reference(
                geometry,
                source_index=source_index,
                max_distance=max_distance,
            )

        best_index: int | None = None
        best_distance: float | None = None
        for raw_index, raw_distance in zip(raw_indices, raw_distances, strict=True):
            candidate_index = int(raw_index)
            distance = float(raw_distance)
            if not 0 <= candidate_index < len(self._geometries) or not math.isfinite(distance):
                return self._nearest_reference(
                    geometry,
                    source_index=source_index,
                    max_distance=max_distance,
                )
            if (
                best_distance is None
                or distance < best_distance
                or (distance == best_distance and candidate_index < best_index)
            ):
                best_index = candidate_index
                best_distance = distance

        if best_index is None or best_distance is None:
            return None
        if max_distance is not None and best_distance > max_distance:
            return None
        return best_index, best_distance

    def covering_indices(
        self,
        point: BaseGeometry,
        *,
        point_index: int,
    ) -> tuple[int, ...]:
        """Return covering polygon indices in original input order."""
        if self._tree is None:
            return ()
        try:
            raw_indices = _query_covered_by(self._tree, point)
        except GEOSException:
            return self._covering_reference(point, point_index=point_index)

        indices = {int(raw_index) for raw_index in raw_indices}
        if any(index < 0 or index >= len(self._geometries) for index in indices):
            raise RuntimeError("STRtree returned an out-of-range geometry index")
        return tuple(sorted(indices))

    def intersecting_indices(
        self,
        geometry: BaseGeometry,
        *,
        source_index: int,
    ) -> tuple[int, ...]:
        """Return exact intersecting candidate indices in original input order."""
        if self._tree is None:
            return ()
        try:
            raw_indices = _query_intersects(self._tree, geometry)
        except GEOSException:
            return self._intersecting_reference(geometry, source_index=source_index)

        indices = {int(raw_index) for raw_index in raw_indices}
        if any(index < 0 or index >= len(self._geometries) for index in indices):
            raise RuntimeError("STRtree returned an out-of-range geometry index")
        return tuple(sorted(indices))

    def _nearest_reference(
        self,
        geometry: BaseGeometry,
        *,
        source_index: int,
        max_distance: float | None,
    ) -> tuple[int, float] | None:
        best_index: int | None = None
        best_distance: float | None = None
        for candidate_index, candidate_geometry in enumerate(self._geometries):
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
            if best_distance is None or distance < best_distance:
                best_index = candidate_index
                best_distance = distance

        if best_index is None or best_distance is None:
            return None
        if max_distance is not None and best_distance > max_distance:
            return None
        return best_index, best_distance

    def _intersecting_reference(
        self,
        geometry: BaseGeometry,
        *,
        source_index: int,
    ) -> tuple[int, ...]:
        matches: list[int] = []
        for candidate_index, candidate_geometry in enumerate(self._geometries):
            try:
                intersects = geometry.intersects(candidate_geometry)
            except GEOSException as exc:
                raise ValidationError(
                    "intersection candidate query failed for left feature "
                    f"{source_index} and right feature {candidate_index}"
                ) from exc
            if intersects:
                matches.append(candidate_index)
        return tuple(matches)

    def _covering_reference(
        self,
        point: BaseGeometry,
        *,
        point_index: int,
    ) -> tuple[int, ...]:
        matches: list[int] = []
        for polygon_index, polygon in enumerate(self._geometries):
            try:
                covered = polygon.covers(point)
            except GEOSException as exc:
                raise ValidationError(
                    "point-in-polygon join failed for point feature "
                    f"{point_index} and polygon {polygon_index}"
                ) from exc
            if covered:
                matches.append(polygon_index)
        return tuple(matches)


__all__ = ["DeterministicSpatialIndex"]
