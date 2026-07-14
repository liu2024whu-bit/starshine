from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CORPUS_VERSION = 2
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


def build_cases() -> tuple[BenchmarkCase, ...]:
    """Create the complete deterministic benchmark corpus from scratch."""
    return (
        _buffer_case(),
        _dissolve_case(),
        _summary_case(),
        _multi_step_case(),
        _clip_case(),
    )
