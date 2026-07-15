from copy import deepcopy

import pytest

from starshine_geo import join_points_to_polygons, plan_workflow, run_workflow
from starshine_geo.errors import ValidationError, WorkflowValidationError


def _collection(features, crs="EPSG:3857"):
    value = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        value["starshine:crs"] = crs
    return value


def _point(x, y, **properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [x, y]},
    }


def _polygon(min_x, min_y, max_x, max_y, **properties):
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


def _workflow(parameters=None):
    return {
        "version": 1,
        "steps": [
            {
                "operation": "join_points_to_polygons",
                "inputs": {"points": "points", "polygons": "polygons"},
                "parameters": (
                    parameters if parameters is not None else {"polygon_id_field": "zone_id"}
                ),
                "output": "joined",
            }
        ],
    }


def test_join_preserves_point_order_properties_geometry_and_matches_interiors():
    points = _collection(
        [
            _point(2, 2, point_id="west"),
            _point(12, 2, point_id="east"),
            _point(30, 2, point_id="outside"),
        ]
    )
    polygons = _collection(
        [
            _polygon(0, 0, 10, 10, zone_id="zone-west"),
            _polygon(10, 0, 20, 10, zone_id="zone-east"),
        ]
    )

    result = join_points_to_polygons(
        points,
        polygons,
        polygon_id_field="zone_id",
        output_field="joined_zone",
        unmatched_value="unassigned",
    )

    assert result["starshine:crs"] == "EPSG:3857"
    assert [feature["properties"]["point_id"] for feature in result["features"]] == [
        "west",
        "east",
        "outside",
    ]
    assert [feature["properties"]["joined_zone"] for feature in result["features"]] == [
        "zone-west",
        "zone-east",
        "unassigned",
    ]
    assert [feature["geometry"]["coordinates"] for feature in result["features"]] == [
        (2.0, 2.0),
        (12.0, 2.0),
        (30.0, 2.0),
    ]


def test_boundary_is_inclusive_and_first_policy_is_explicitly_deterministic():
    points = _collection([_point(10, 5, point_id="boundary")])
    polygons = _collection(
        [
            _polygon(0, 0, 10, 10, zone_id="west-first"),
            _polygon(10, 0, 20, 10, zone_id="east-second"),
        ]
    )

    with pytest.raises(ValidationError, match="matches multiple polygons"):
        join_points_to_polygons(
            points,
            polygons,
            polygon_id_field="zone_id",
        )

    result = join_points_to_polygons(
        points,
        polygons,
        polygon_id_field="zone_id",
        multiple_match="first",
    )
    assert result["features"][0]["properties"]["polygon_id"] == "west-first"


def test_empty_polygons_retain_points_with_explicit_unmatched_value():
    result = join_points_to_polygons(
        _collection([_point(1, 1, point_id="only")]),
        _collection([]),
        polygon_id_field="zone_id",
        unmatched_value=0,
    )

    assert result["features"][0]["properties"] == {
        "point_id": "only",
        "polygon_id": 0,
    }


def test_join_allows_equivalent_geographic_crs_for_topological_containment():
    result = join_points_to_polygons(
        _collection([_point(0.5, 0.5, point_id="inside")], crs="EPSG:4326"),
        _collection(
            [_polygon(0, 0, 1, 1, zone_id="degree-zone")],
            crs="EPSG:4326",
        ),
        polygon_id_field="zone_id",
    )
    assert result["features"][0]["properties"]["polygon_id"] == "degree-zone"


@pytest.mark.parametrize("missing_label", ["points", "polygons"])
def test_join_requires_declared_crs(missing_label):
    points = _collection([_point(1, 1, point_id="point")])
    polygons = _collection([_polygon(0, 0, 2, 2, zone_id="zone")])
    if missing_label == "points":
        points.pop("starshine:crs")
    else:
        polygons.pop("starshine:crs")

    with pytest.raises(ValidationError, match=f"{missing_label} collection must declare"):
        join_points_to_polygons(points, polygons, polygon_id_field="zone_id")


def test_join_requires_equivalent_crs_values():
    with pytest.raises(ValidationError, match="equivalent CRS"):
        join_points_to_polygons(
            _collection([_point(1, 1)], crs="EPSG:3857"),
            _collection([_polygon(0, 0, 2, 2, zone_id="zone")], crs="EPSG:4326"),
            polygon_id_field="zone_id",
        )


def test_join_requires_point_and_polygon_geometry_types():
    with pytest.raises(ValidationError, match="Point geometry only"):
        join_points_to_polygons(
            _collection([_polygon(0, 0, 1, 1, point_id="not-point")]),
            _collection([_polygon(0, 0, 2, 2, zone_id="zone")]),
            polygon_id_field="zone_id",
        )

    with pytest.raises(ValidationError, match="Polygon or MultiPolygon"):
        join_points_to_polygons(
            _collection([_point(1, 1, point_id="point")]),
            _collection([_point(1, 1, zone_id="not-polygon")]),
            polygon_id_field="zone_id",
        )


@pytest.mark.parametrize(
    ("polygon_features", "message"),
    [
        ([_polygon(0, 0, 2, 2)], "missing required property"),
        (
            [
                _polygon(0, 0, 2, 2, zone_id="duplicate"),
                _polygon(3, 0, 5, 2, zone_id="duplicate"),
            ],
            "duplicate polygon identifier",
        ),
        ([_polygon(0, 0, 2, 2, zone_id=None)], "non-null JSON scalar"),
        ([_polygon(0, 0, 2, 2, zone_id=["nested"])], "JSON scalar"),
    ],
)
def test_join_rejects_invalid_polygon_identifiers(polygon_features, message):
    with pytest.raises(ValidationError, match=message):
        join_points_to_polygons(
            _collection([_point(1, 1, point_id="point")]),
            _collection(polygon_features),
            polygon_id_field="zone_id",
        )


@pytest.mark.parametrize("unmatched_value", [[], {}, float("inf"), float("nan"), object()])
def test_join_rejects_non_json_or_non_finite_unmatched_values(unmatched_value):
    with pytest.raises(ValidationError, match="unmatched_value"):
        join_points_to_polygons(
            _collection([_point(1, 1, point_id="point")]),
            _collection([]),
            polygon_id_field="zone_id",
            unmatched_value=unmatched_value,
        )


def test_join_rejects_invalid_policy_and_output_field_collisions():
    points = _collection([_point(1, 1, point_id="point", polygon_id="occupied")])
    polygons = _collection([_polygon(0, 0, 2, 2, zone_id="zone")])

    with pytest.raises(ValidationError, match="already contains output property"):
        join_points_to_polygons(points, polygons, polygon_id_field="zone_id")

    for invalid_policy in ("all", ["first"]):
        with pytest.raises(ValidationError, match="multiple_match"):
            join_points_to_polygons(
                _collection([_point(1, 1, point_id="point")]),
                polygons,
                polygon_id_field="zone_id",
                multiple_match=invalid_policy,
            )


def test_join_workflow_and_plan_share_registry_defaults():
    points = _collection([_point(1, 1, point_id="point")])
    polygons = _collection([_polygon(0, 0, 2, 2, zone_id="zone")])
    workflow = _workflow()

    result = run_workflow(workflow, {"points": points, "polygons": polygons})
    assert result["joined"]["features"][0]["properties"]["polygon_id"] == "zone"

    plan = plan_workflow(workflow, {"points", "polygons", "unused"})
    step = plan["steps"][0]
    assert step["parameters"] == {
        "polygon_id_field": "zone_id",
        "output_field": "polygon_id",
        "unmatched_value": None,
        "multiple_match": "error",
    }
    assert step["parameter_sources"] == {
        "polygon_id_field": "provided",
        "output_field": "default",
        "unmatched_value": "default",
        "multiple_match": "default",
    }
    assert plan["required_external_layers"] == ["points", "polygons"]
    assert plan["unused_external_layers"] == ["unused"]


def test_join_workflow_parameter_diagnostic_is_stable():
    workflow = _workflow(
        {
            "polygon_id_field": "zone_id",
            "multiple_match": "all",
        }
    )
    with pytest.raises(WorkflowValidationError) as exc_info:
        plan_workflow(workflow, {"points", "polygons"})

    assert exc_info.value.diagnostic.as_dict() == {
        "code": "invalid_parameter",
        "message": "join_points_to_polygons.multiple_match must be 'error' or 'first'",
        "path": "steps[0].parameters.multiple_match",
        "step_index": 0,
        "operation": "join_points_to_polygons",
    }


def test_join_does_not_mutate_inputs():
    points = _collection([_point(1, 1, point_id="point")])
    polygons = _collection([_polygon(0, 0, 2, 2, zone_id="zone")])
    points_before = deepcopy(points)
    polygons_before = deepcopy(polygons)

    join_points_to_polygons(points, polygons, polygon_id_field="zone_id")

    assert points == points_before
    assert polygons == polygons_before
