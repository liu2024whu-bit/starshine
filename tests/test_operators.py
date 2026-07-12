from __future__ import annotations

import pytest

from starshine_geo.errors import ValidationError
from starshine_geo.operators import buffer_features, summarize_points_within


@pytest.fixture
def zones():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"id": "a"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
                },
            }
        ],
    }


@pytest.fixture
def points():
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [1, 1]}},
            {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [20, 20]}},
        ],
    }


def test_summarize_points_within_counts_only_covered_points(zones, points):
    result = summarize_points_within(zones, points)
    assert result["features"][0]["properties"]["point_count"] == 1


def test_summarize_points_within_rejects_non_points(zones):
    with pytest.raises(ValidationError, match="Point geometry"):
        summarize_points_within(zones, zones)


def test_buffer_requires_projected_work_crs(points):
    with pytest.raises(ValidationError, match="projected CRS"):
        buffer_features(
            points,
            distance=100,
            source_crs="EPSG:4326",
            work_crs="EPSG:4326",
        )


def test_buffer_round_trip_returns_polygon(points):
    result = buffer_features(
        points,
        distance=100,
        source_crs="EPSG:4326",
        work_crs="EPSG:3857",
    )
    assert result["features"][0]["geometry"]["type"] == "Polygon"
