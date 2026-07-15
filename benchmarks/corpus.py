from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CORPUS_VERSION = 5
CRS = "EPSG:3857"
JsonObject = dict[str, Any]
FeatureCollection = dict[str, Any]


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One deterministic workflow case built only from synthetic public inputs."""

    name: str
    description: str
    workflow: JsonObject
    layers: dict[str, FeatureCollection]
    output_layer: str
    expected_signature: JsonObject

    @property
    def input_feature_count(self) -> int:
        return sum(len(layer["features"]) for layer in self.layers.values())

    @property
    def operation_count(self) -> int:
        return len(self.workflow["steps"])

    def definition(self) -> JsonObject:
        """Return the stable public inputs and expected semantics for this case."""
        return {
            "name": self.name,
            "workflow": self.workflow,
            "layers": self.layers,
            "output_layer": self.output_layer,
            "expected_signature": self.expected_signature,
        }


def _point(x: float, y: float, **properties: Any) -> JsonObject:
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [x, y]},
    }


def _square(x: float, y: float, size: float, **properties: Any) -> JsonObject:
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [x, y],
                    [x + size, y],
                    [x + size, y + size],
                    [x, y + size],
                    [x, y],
                ]
            ],
        },
    }


def _rectangle(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    **properties: Any,
) -> JsonObject:
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [min_x, min_y],
                    [max_x, min_y],
                    [max_x, max_y],
                    [min_x, max_y],
                    [min_x, min_y],
                ]
            ],
        },
    }


def _collection(features: list[JsonObject]) -> FeatureCollection:
    return {"type": "FeatureCollection", "starshine:crs": CRS, "features": features}


def _buffer_case() -> BenchmarkCase:
    features = [
        _point(column * 25.0, row * 25.0, site_id=f"site-{row:02d}-{column:02d}")
        for row in range(8)
        for column in range(8)
    ]
    return BenchmarkCase(
        name="buffer-grid-64",
        description="Buffer a deterministic 8 by 8 point grid in a projected CRS.",
        workflow={
            "version": 1,
            "steps": [
                {
                    "operation": "buffer",
                    "inputs": {"input": "sites"},
                    "parameters": {
                        "distance": 5.0,
                        "source_crs": CRS,
                        "work_crs": CRS,
                        "segments": 4,
                    },
                    "output": "site_buffers",
                }
            ],
        },
        layers={"sites": _collection(features)},
        output_layer="site_buffers",
        expected_signature={
            "crs": CRS,
            "feature_count": 64,
            "geometry_types": ["Polygon"],
            "buffer_distance": 5.0,
            "work_crs": CRS,
        },
    )


def _dissolve_case() -> BenchmarkCase:
    features = [
        _square(
            column * 10.0,
            row * 10.0,
            10.0,
            cell_id=f"cell-{row:02d}-{column:02d}",
            band=f"band-{row % 4}",
        )
        for row in range(8)
        for column in range(10)
    ]
    return BenchmarkCase(
        name="dissolve-bands-80",
        description="Dissolve 80 adjacent squares into four deterministic row bands.",
        workflow={
            "version": 1,
            "steps": [
                {
                    "operation": "dissolve",
                    "inputs": {"input": "cells"},
                    "parameters": {"group_field": "band"},
                    "output": "bands",
                }
            ],
        },
        layers={"cells": _collection(features)},
        output_layer="bands",
        expected_signature={
            "crs": CRS,
            "feature_count": 4,
            "bands": ["band-0", "band-1", "band-2", "band-3"],
        },
    )


def _metrics_case() -> BenchmarkCase:
    polygons = [
        _square(column * 12.0, row * 12.0, 10.0, cell_id=f"metric-{row}-{column}")
        for row in range(5)
        for column in range(5)
    ]
    return BenchmarkCase(
        name="geometry-metrics-grid-25",
        description="Calculate projected area and boundary length for 25 synthetic squares.",
        workflow={
            "version": 1,
            "steps": [
                {
                    "operation": "geometry_metrics",
                    "inputs": {"input": "cells"},
                    "parameters": {"area_field": "area_m2", "length_field": "perimeter_m"},
                    "output": "measured_cells",
                }
            ],
        },
        layers={"cells": _collection(polygons)},
        output_layer="measured_cells",
        expected_signature={
            "crs": CRS,
            "feature_count": 25,
            "areas": [100.0] * 25,
            "lengths": [40.0] * 25,
        },
    )


def _summary_case() -> BenchmarkCase:
    zones: list[JsonObject] = []
    sites: list[JsonObject] = []
    for row in range(4):
        for column in range(4):
            origin_x = column * 100.0
            origin_y = row * 100.0
            zone_id = f"zone-{row}-{column}"
            zones.append(_square(origin_x, origin_y, 100.0, zone_id=zone_id))
            for offset_x, offset_y in (
                (25.0, 25.0),
                (25.0, 75.0),
                (75.0, 25.0),
                (75.0, 75.0),
            ):
                sites.append(
                    _point(
                        origin_x + offset_x,
                        origin_y + offset_y,
                        zone_hint=zone_id,
                    )
                )
    return BenchmarkCase(
        name="summarize-zones-16-sites-64",
        description="Count 64 synthetic points inside 16 non-overlapping study zones.",
        workflow={
            "version": 1,
            "steps": [
                {
                    "operation": "summarize_points_within",
                    "inputs": {"polygons": "zones", "points": "sites"},
                    "parameters": {
                        "polygon_id_field": "zone_id",
                        "count_field": "site_count",
                    },
                    "output": "zone_summary",
                }
            ],
        },
        layers={"zones": _collection(zones), "sites": _collection(sites)},
        output_layer="zone_summary",
        expected_signature={
            "crs": CRS,
            "feature_count": 16,
            "zone_counts": [
                [f"zone-{row}-{column}", 4]
                for row in range(4)
                for column in range(4)
            ],
        },
    )


def _multi_step_case() -> BenchmarkCase:
    features = [
        _point(column * 20.0, row * 20.0, site_id=f"multi-{row:02d}-{column:02d}")
        for row in range(6)
        for column in range(6)
    ]
    return BenchmarkCase(
        name="multi-step-buffer-dissolve-36",
        description="Buffer a 6 by 6 point grid and dissolve the connected result.",
        workflow={
            "version": 1,
            "steps": [
                {
                    "operation": "buffer",
                    "inputs": {"input": "sites"},
                    "parameters": {
                        "distance": 12.0,
                        "source_crs": CRS,
                        "work_crs": CRS,
                        "segments": 4,
                    },
                    "output": "buffers",
                },
                {
                    "operation": "dissolve",
                    "inputs": {"input": "buffers"},
                    "parameters": {},
                    "output": "coverage",
                },
            ],
        },
        layers={"sites": _collection(features)},
        output_layer="coverage",
        expected_signature={"crs": CRS, "feature_count": 1},
    )


def _clip_case() -> BenchmarkCase:
    cells = [
        _square(
            column * 10.0,
            row * 10.0,
            10.0,
            cell_id=f"cell-{row}-{column}",
        )
        for row in range(5)
        for column in range(5)
    ]
    mask = [_rectangle(12.0, 7.0, 38.0, 33.0, mask_id="central-window")]
    retained_ids = [
        f"cell-{row}-{column}"
        for row in range(4)
        for column in range(1, 4)
    ]
    return BenchmarkCase(
        name="clip-grid-25",
        description="Clip a deterministic 5 by 5 polygon grid with one offset rectangular mask.",
        workflow={
            "version": 1,
            "steps": [
                {
                    "operation": "clip",
                    "inputs": {"input": "cells", "mask": "mask"},
                    "parameters": {},
                    "output": "clipped_cells",
                }
            ],
        },
        layers={"cells": _collection(cells), "mask": _collection(mask)},
        output_layer="clipped_cells",
        expected_signature={
            "crs": CRS,
            "feature_count": 12,
            "geometry_types": ["Polygon"],
            "cell_ids": retained_ids,
            "bbox": [12.0, 7.0, 38.0, 33.0],
        },
    )


def _join_case() -> BenchmarkCase:
    polygons: list[JsonObject] = []
    points: list[JsonObject] = []
    expected_assignments: list[list[str]] = []
    for row in range(4):
        for column in range(4):
            origin_x = column * 100.0
            origin_y = row * 100.0
            zone_id = f"zone-{row}-{column}"
            polygons.append(_square(origin_x, origin_y, 100.0, zone_id=zone_id))
            for point_index, (offset_x, offset_y) in enumerate(
                (
                    (20.0, 20.0),
                    (20.0, 80.0),
                    (80.0, 20.0),
                    (80.0, 80.0),
                )
            ):
                point_id = f"point-{row}-{column}-{point_index}"
                points.append(
                    _point(
                        origin_x + offset_x,
                        origin_y + offset_y,
                        point_id=point_id,
                    )
                )
                expected_assignments.append([point_id, zone_id])

    return BenchmarkCase(
        name="join-points-64-zones-16",
        description="Join 64 synthetic points to 16 non-overlapping polygon zones.",
        workflow={
            "version": 1,
            "steps": [
                {
                    "operation": "join_points_to_polygons",
                    "inputs": {"points": "points", "polygons": "zones"},
                    "parameters": {
                        "polygon_id_field": "zone_id",
                        "output_field": "joined_zone",
                    },
                    "output": "joined_points",
                }
            ],
        },
        layers={"points": _collection(points), "zones": _collection(polygons)},
        output_layer="joined_points",
        expected_signature={
            "crs": CRS,
            "feature_count": 64,
            "assignments": expected_assignments,
        },
    )

def _nearest_case() -> BenchmarkCase:
    sources = [
        _point(
            column * 10.0,
            row * 10.0,
            source_id=f"source-{row}-{column}",
        )
        for row in range(6)
        for column in range(6)
    ]
    candidates = [
        _point(
            column * 20.0,
            row * 20.0,
            candidate_id=f"candidate-{row}-{column}",
        )
        for row in range(3)
        for column in range(3)
    ]
    candidate_positions = [
        (
            feature["properties"]["candidate_id"],
            float(feature["geometry"]["coordinates"][0]),
            float(feature["geometry"]["coordinates"][1]),
        )
        for feature in candidates
    ]
    expected_matches = []
    for feature in sources:
        source_id = feature["properties"]["source_id"]
        source_x, source_y = feature["geometry"]["coordinates"]
        nearest_id = None
        nearest_distance = None
        for candidate_id, candidate_x, candidate_y in candidate_positions:
            distance = ((source_x - candidate_x) ** 2 + (source_y - candidate_y) ** 2) ** 0.5
            if nearest_distance is None or distance < nearest_distance:
                nearest_id = candidate_id
                nearest_distance = distance
        expected_matches.append([source_id, nearest_id, round(float(nearest_distance), 6)])

    return BenchmarkCase(
        name="nearest-grid-36-candidates-9",
        description=(
            "Match a 6 by 6 projected source grid to a 3 by 3 candidate grid with stable ties."
        ),
        workflow={
            "version": 1,
            "steps": [
                {
                    "operation": "nearest",
                    "inputs": {"source": "sources", "candidates": "candidates"},
                    "parameters": {"candidate_id_field": "candidate_id"},
                    "output": "nearest_matches",
                }
            ],
        },
        layers={
            "sources": _collection(sources),
            "candidates": _collection(candidates),
        },
        output_layer="nearest_matches",
        expected_signature={
            "crs": CRS,
            "feature_count": 36,
            "matches": expected_matches,
        },
    )


def build_cases() -> tuple[BenchmarkCase, ...]:
    """Create the complete deterministic benchmark corpus from scratch."""
    return (
        _buffer_case(),
        _dissolve_case(),
        _metrics_case(),
        _summary_case(),
        _multi_step_case(),
        _clip_case(),
        _join_case(),
        _nearest_case(),
    )
