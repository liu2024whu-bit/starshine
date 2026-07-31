from __future__ import annotations

from copy import deepcopy

import pytest
from shapely import STRtree
from shapely.errors import GEOSException
from shapely.geometry import shape

import starshine_geo._spatial_index as spatial_index_module
from starshine_geo import join_points_to_polygons, nearest_features
from starshine_geo._spatial_index import DeterministicSpatialIndex
from starshine_geo.errors import ValidationError

CRS = "EPSG:3857"


def _collection(features):
    return {"type": "FeatureCollection", "starshine:crs": CRS, "features": features}


def _point(x, y, **properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [x, y]},
    }


def _square(min_x, min_y, size, **properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [min_x, min_y],
                    [min_x + size, min_y],
                    [min_x + size, min_y + size],
                    [min_x, min_y + size],
                    [min_x, min_y],
                ]
            ],
        },
    }


def _reference_nearest(source, candidates, *, max_distance):
    candidate_records = [
        (feature["properties"]["candidate_id"], shape(feature["geometry"]))
        for feature in candidates["features"]
    ]
    expected = []
    for feature in source["features"]:
        source_geometry = shape(feature["geometry"])
        best_id = None
        best_distance = None
        for candidate_id, candidate_geometry in candidate_records:
            distance = float(source_geometry.distance(candidate_geometry))
            if best_distance is None or distance < best_distance:
                best_id = candidate_id
                best_distance = distance
        if best_distance is None or (
            max_distance is not None and best_distance > max_distance
        ):
            best_id = None
            best_distance = None
        expected.append((best_id, best_distance))
    return expected


def _reference_join(points, polygons):
    polygon_records = [
        (feature["properties"]["zone_id"], shape(feature["geometry"]))
        for feature in polygons["features"]
    ]
    expected = []
    for feature in points["features"]:
        point = shape(feature["geometry"])
        matches = [identifier for identifier, polygon in polygon_records if polygon.covers(point)]
        expected.append(matches)
    return expected


@pytest.mark.parametrize("max_distance", [None, 0.0, 5.0, 12.5, 100.0])
def test_indexed_nearest_matches_independent_bruteforce_reference(max_distance):
    source = _collection(
        [
            _point(column * 7.0 + (row % 2) * 0.5, row * 6.0, source_id=f"s-{row}-{column}")
            for row in range(12)
            for column in range(13)
        ]
    )
    candidates = _collection(
        [
            _point(column * 14.0, row * 12.0, candidate_id=f"c-{row}-{column}")
            for row in range(7)
            for column in range(7)
        ]
    )
    candidates["features"].append(_point(0.0, 0.0, candidate_id="duplicate-later"))

    result = nearest_features(
        source,
        candidates,
        candidate_id_field="candidate_id",
        max_distance=max_distance,
    )
    expected = _reference_nearest(source, candidates, max_distance=max_distance)

    assert [
        (
            feature["properties"]["nearest_id"],
            feature["properties"]["nearest_distance"],
        )
        for feature in result["features"]
    ] == expected


def test_indexed_point_join_matches_reference_for_interiors_boundaries_and_overlaps():
    polygons = _collection(
        [
            _square(0, 0, 10, zone_id="first"),
            _square(10, 0, 10, zone_id="east"),
            _square(5, 5, 10, zone_id="overlap-later"),
        ]
    )
    points = _collection(
        [
            _point(1, 1, point_id="interior"),
            _point(10, 2, point_id="shared-boundary"),
            _point(7, 7, point_id="overlap"),
            _point(30, 30, point_id="unmatched"),
        ]
    )
    expected = _reference_join(points, polygons)

    first = join_points_to_polygons(
        points,
        polygons,
        polygon_id_field="zone_id",
        output_field="zone",
        unmatched_value="outside",
        multiple_match="first",
    )
    assert [feature["properties"]["zone"] for feature in first["features"]] == [
        matches[0] if matches else "outside" for matches in expected
    ]

    with pytest.raises(ValidationError, match="matches multiple polygons"):
        join_points_to_polygons(
            points,
            polygons,
            polygon_id_field="zone_id",
            multiple_match="error",
        )


def test_strtree_return_order_is_never_public_semantics(monkeypatch):
    geometries = [shape(_point(x, 0)["geometry"]) for x in (-1, 1, 4)]
    index = DeterministicSpatialIndex(geometries)

    monkeypatch.setattr(
        spatial_index_module,
        "_query_nearest",
        lambda tree, geometry, *, max_distance: ([2, 1, 0], [4.0, 1.0, 1.0]),
    )
    assert index.nearest_first(geometries[1].centroid, source_index=0, max_distance=None) == (
        0,
        1.0,
    )

    monkeypatch.setattr(
        spatial_index_module,
        "_query_covered_by",
        lambda tree, geometry: [2, 0, 1, 1],
    )
    assert index.covering_indices(geometries[0], point_index=0) == (0, 1, 2)


def test_expected_geos_query_failures_use_reference_semantics(monkeypatch):
    source = _collection([_point(0, 0, source_id="source")])
    candidates = _collection(
        [
            _point(-1, 0, candidate_id="first"),
            _point(1, 0, candidate_id="second"),
        ]
    )
    polygons = _collection([_square(0, 0, 10, zone_id="zone")])
    points = _collection([_point(0, 5, point_id="boundary")])

    def fail_query(*args, **kwargs):
        raise GEOSException("synthetic indexed query failure")

    monkeypatch.setattr(spatial_index_module, "_query_nearest", fail_query)
    nearest = nearest_features(source, candidates, candidate_id_field="candidate_id")
    assert nearest["features"][0]["properties"]["nearest_id"] == "first"

    monkeypatch.setattr(spatial_index_module, "_query_covered_by", fail_query)
    joined = join_points_to_polygons(points, polygons, polygon_id_field="zone_id")
    assert joined["features"][0]["properties"]["polygon_id"] == "zone"


def test_unexpected_index_errors_are_not_hidden(monkeypatch):
    source = _collection([_point(0, 0, source_id="source")])
    candidates = _collection([_point(1, 0, candidate_id="candidate")])

    def fail_unexpected(*args, **kwargs):
        raise RuntimeError("programming defect")

    monkeypatch.setattr(spatial_index_module, "_query_nearest", fail_unexpected)
    with pytest.raises(RuntimeError, match="programming defect"):
        nearest_features(source, candidates, candidate_id_field="candidate_id")


def test_one_tree_is_built_per_public_operation(monkeypatch):
    original_tree = STRtree
    built_sizes = []

    def counting_tree(geometries):
        values = tuple(geometries)
        built_sizes.append(len(values))
        return original_tree(values)

    monkeypatch.setattr(spatial_index_module, "STRtree", counting_tree)

    source = _collection([_point(index, 0, source_id=index) for index in range(30)])
    candidates = _collection(
        [_point(index * 2, 0, candidate_id=index) for index in range(10)]
    )
    nearest_features(source, candidates, candidate_id_field="candidate_id")

    points = _collection([_point(index + 0.5, 0.5, point_id=index) for index in range(20)])
    polygons = _collection([_square(index, 0, 1, zone_id=index) for index in range(20)])
    join_points_to_polygons(points, polygons, polygon_id_field="zone_id")

    assert built_sizes == [10, 20]


def test_indexed_operators_do_not_mutate_generated_inputs():
    source = _collection([_point(0, 0, source_id="source")])
    candidates = _collection([_point(1, 0, candidate_id="candidate")])
    points = _collection([_point(0, 0, point_id="point")])
    polygons = _collection([_square(0, 0, 1, zone_id="zone")])
    before = deepcopy((source, candidates, points, polygons))

    nearest_features(source, candidates, candidate_id_field="candidate_id")
    join_points_to_polygons(points, polygons, polygon_id_field="zone_id")

    assert (source, candidates, points, polygons) == before
