from __future__ import annotations

from copy import deepcopy

import pytest
from shapely.errors import GEOSException
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

import starshine_geo._spatial_index as spatial_index_module
from starshine_geo import (
    build_workflow_contract,
    intersect_features,
    plan_workflow,
    preflight_workflow_inputs,
    run_workflow,
)
from starshine_geo.errors import ValidationError

CRS = "EPSG:3857"


def _collection(features, crs=CRS):
    value = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        value["starshine:crs"] = crs
    return value


def _polygon(min_x, min_y, max_x, max_y, **properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [min_x, min_y],
                [max_x, min_y],
                [max_x, max_y],
                [min_x, max_y],
                [min_x, min_y],
            ]],
        },
    }


def _line(x1, y1, x2, y2, **properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "LineString", "coordinates": [[x1, y1], [x2, y2]]},
    }


def _point(x, y, **properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [x, y]},
    }


def _reference_intersection(left, right, *, right_id_field, output_field="intersection_id"):
    output = []
    right_records = [
        (feature["properties"][right_id_field], shape(feature["geometry"]))
        for feature in right["features"]
    ]
    for left_feature in left["features"]:
        left_geometry = shape(left_feature["geometry"])
        for right_identifier, right_geometry in right_records:
            if not left_geometry.intersects(right_geometry):
                continue
            intersection = left_geometry.intersection(right_geometry)
            if intersection.is_empty:
                continue
            properties = dict(left_feature.get("properties") or {})
            properties[output_field] = right_identifier
            output.append(
                {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": mapping(intersection.normalize()),
                }
            )
    return {
        "type": "FeatureCollection",
        "features": output,
        "starshine:crs": left["starshine:crs"],
    }


def _workflow():
    return {
        "version": 1,
        "steps": [
            {
                "operation": "intersection",
                "inputs": {"left": "left", "right": "right"},
                "parameters": {"right_id_field": "zone_id"},
                "output": "intersections",
            }
        ],
    }


def test_intersection_emits_stable_pair_order_and_retains_boundary_results():
    left = _collection([
        _polygon(0, 0, 10, 10, parcel_id="a"),
        _polygon(10, 0, 20, 10, parcel_id="b"),
    ])
    right = _collection([
        _polygon(5, -2, 15, 12, zone_id="middle"),
        _polygon(20, 0, 30, 10, zone_id="east-touch"),
    ])

    result = intersect_features(left, right, right_id_field="zone_id")

    assert [feature["properties"] for feature in result["features"]] == [
        {"parcel_id": "a", "intersection_id": "middle"},
        {"parcel_id": "b", "intersection_id": "middle"},
        {"parcel_id": "b", "intersection_id": "east-touch"},
    ]
    assert [feature["geometry"]["type"] for feature in result["features"]] == [
        "Polygon",
        "Polygon",
        "LineString",
    ]
    assert result["starshine:crs"] == CRS


def test_intersection_matches_independent_exhaustive_reference_on_generated_grid():
    left = _collection([
        _polygon(column * 9, row * 9, column * 9 + 7, row * 9 + 7, parcel_id=f"p-{row}-{column}")
        for row in range(8)
        for column in range(9)
    ])
    right = _collection([
        _polygon(column * 18 + 1, row * 18 + 1, column * 18 + 16, row * 18 + 16, zone_id=f"z-{row}-{column}")
        for row in range(4)
        for column in range(5)
    ])

    indexed = intersect_features(left, right, right_id_field="zone_id", output_field="zone")
    reference = _reference_intersection(
        left, right, right_id_field="zone_id", output_field="zone"
    )
    assert indexed == reference


def test_intersection_supports_mixed_geometry_and_empty_result():
    left = _collection([
        _line(-5, 5, 15, 5, road="crossing"),
        _point(5, 5, station="inside"),
        _point(50, 50, station="outside"),
    ])
    right = _collection([_polygon(0, 0, 10, 10, zone_id="zone")])

    result = intersect_features(left, right, right_id_field="zone_id", output_field="zone")
    assert [feature["geometry"]["type"] for feature in result["features"]] == [
        "LineString",
        "Point",
    ]
    assert [feature["properties"]["zone"] for feature in result["features"]] == [
        "zone",
        "zone",
    ]

    empty = intersect_features(
        _collection([_point(100, 100, id="outside")]),
        right,
        right_id_field="zone_id",
    )
    assert empty == {"type": "FeatureCollection", "features": [], "starshine:crs": CRS}


@pytest.mark.parametrize("missing", ["left", "right"])
def test_intersection_requires_declared_crs(missing):
    left = _collection([_point(1, 1, id="left")])
    right = _collection([_polygon(0, 0, 2, 2, zone_id="zone")])
    if missing == "left":
        left.pop("starshine:crs")
    else:
        right.pop("starshine:crs")
    with pytest.raises(ValidationError, match=f"{missing} collection must declare starshine:crs"):
        intersect_features(left, right, right_id_field="zone_id")


def test_intersection_requires_equivalent_crs():
    left = _collection([_point(1, 1, id="left")], crs="EPSG:3857")
    right = _collection([_polygon(0, 0, 2, 2, zone_id="zone")], crs="EPSG:4326")
    with pytest.raises(ValidationError, match="intersection inputs must declare equivalent CRS"):
        intersect_features(left, right, right_id_field="zone_id")


@pytest.mark.parametrize(
    ("right_features", "message"),
    [
        ([_polygon(0, 0, 2, 2)], "missing required property"),
        ([_polygon(0, 0, 2, 2, zone_id=None)], "must be a non-null JSON scalar"),
        ([_polygon(0, 0, 2, 2, zone_id=float("inf"))], "must be a finite JSON scalar"),
        (
            [
                _polygon(0, 0, 2, 2, zone_id="same"),
                _polygon(3, 0, 5, 2, zone_id="same"),
            ],
            "duplicate right identifier",
        ),
    ],
)
def test_intersection_validates_right_identifiers(right_features, message):
    left = _collection([_point(1, 1, id="left")])
    with pytest.raises(ValidationError, match=message):
        intersect_features(left, _collection(right_features), right_id_field="zone_id")


def test_intersection_rejects_blank_fields_and_left_output_collision():
    left = _collection([_point(1, 1, intersection_id="occupied")])
    right = _collection([_polygon(0, 0, 2, 2, zone_id="zone")])

    with pytest.raises(ValidationError, match="right_id_field must be a non-empty string"):
        intersect_features(left, right, right_id_field="")
    with pytest.raises(ValidationError, match="output_field must be a non-empty string"):
        intersect_features(left, right, right_id_field="zone_id", output_field=" ")
    with pytest.raises(ValidationError, match="already contains output property"):
        intersect_features(left, right, right_id_field="zone_id")


def test_intersection_normalizes_geometry_and_does_not_mutate_or_alias_inputs():
    left = _collection([_polygon(0, 0, 10, 10, parcel_id="p")])
    right = _collection([_polygon(2, 2, 8, 8, zone_id="z")])
    before = deepcopy((left, right))

    first = intersect_features(left, right, right_id_field="zone_id")
    second = intersect_features(left, right, right_id_field="zone_id")

    assert first == second
    assert (left, right) == before
    first["features"][0]["properties"]["parcel_id"] = "changed"
    assert left["features"][0]["properties"]["parcel_id"] == "p"


def test_intersection_is_independent_of_strtree_return_order(monkeypatch):
    left = _collection([_polygon(0, 0, 10, 10, parcel_id="p")])
    right = _collection([
        _polygon(0, 0, 2, 2, zone_id="first"),
        _polygon(3, 0, 5, 2, zone_id="second"),
        _polygon(6, 0, 8, 2, zone_id="third"),
    ])
    monkeypatch.setattr(
        spatial_index_module,
        "_query_intersects",
        lambda tree, geometry: [2, 0, 1, 1],
    )
    result = intersect_features(left, right, right_id_field="zone_id")
    assert [feature["properties"]["intersection_id"] for feature in result["features"]] == [
        "first",
        "second",
        "third",
    ]


def test_expected_index_query_geos_failure_uses_exact_reference(monkeypatch):
    left = _collection([_point(1, 1, id="left")])
    right = _collection([_polygon(0, 0, 2, 2, zone_id="zone")])

    def fail(*args, **kwargs):
        raise GEOSException("synthetic index failure")

    monkeypatch.setattr(spatial_index_module, "_query_intersects", fail)
    result = intersect_features(left, right, right_id_field="zone_id")
    assert result["features"][0]["properties"]["intersection_id"] == "zone"


def test_unexpected_index_errors_are_not_hidden(monkeypatch):
    left = _collection([_point(1, 1, id="left")])
    right = _collection([_polygon(0, 0, 2, 2, zone_id="zone")])

    def fail(*args, **kwargs):
        raise RuntimeError("programming defect")

    monkeypatch.setattr(spatial_index_module, "_query_intersects", fail)
    with pytest.raises(RuntimeError, match="programming defect"):
        intersect_features(left, right, right_id_field="zone_id")


def test_exact_intersection_geos_error_reports_pair_indices(monkeypatch):
    left = _collection([_point(1, 1, id="left")])
    right = _collection([_polygon(0, 0, 2, 2, zone_id="zone")])
    monkeypatch.setattr(
        spatial_index_module,
        "_query_intersects",
        lambda tree, geometry: [0],
    )

    original = BaseGeometry.intersection

    def fail(self, other, grid_size=None):
        raise GEOSException("synthetic exact intersection failure")

    monkeypatch.setattr(BaseGeometry, "intersection", fail)
    try:
        with pytest.raises(
            ValidationError,
            match="intersection failed for left feature 0 and right feature 0",
        ):
            intersect_features(left, right, right_id_field="zone_id")
    finally:
        monkeypatch.setattr(BaseGeometry, "intersection", original)


def test_intersection_workflow_plan_contract_and_preflight_share_registry_defaults():
    left = _collection([_polygon(0, 0, 10, 10, parcel_id="p")])
    right = _collection([_polygon(5, 0, 15, 10, zone_id="z")])
    workflow = _workflow()

    plan = plan_workflow(workflow, {"left", "right"})
    assert plan["steps"][0]["parameters"] == {
        "right_id_field": "zone_id",
        "output_field": "intersection_id",
    }
    assert plan["steps"][0]["parameter_sources"] == {
        "right_id_field": "provided",
        "output_field": "default",
    }

    contract = build_workflow_contract(workflow, {"left", "right"})
    by_name = {layer["name"]: layer for layer in contract["layers"]}
    left_use = by_name["left"]["uses"][0]
    right_use = by_name["right"]["uses"][0]
    assert left_use["written_fields"] == [
        {
            "name": "intersection_id",
            "source_parameter": "output_field",
            "collision_policy": "reject",
        }
    ]
    assert right_use["required_fields"] == [
        {
            "name": "zone_id",
            "source_parameter": "right_id_field",
            "unique": True,
            "non_null": True,
            "finite_json_scalar": True,
        }
    ]

    preflight = preflight_workflow_inputs(workflow, {"left": left, "right": right})
    assert preflight["valid"] is True
    assert preflight["error_count"] == 0

    result = run_workflow(workflow, {"left": left, "right": right})
    assert result["intersections"] == intersect_features(
        left, right, right_id_field="zone_id"
    )
