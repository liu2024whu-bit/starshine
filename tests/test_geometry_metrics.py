from copy import deepcopy

import pytest
from shapely.geometry import shape

from starshine_geo import calculate_geometry_metrics, plan_workflow, run_workflow
from starshine_geo.errors import ValidationError, WorkflowValidationError


def _collection(features, crs="EPSG:3857"):
    value = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        value["starshine:crs"] = crs
    return value


def _feature(geometry, **properties):
    return {"type": "Feature", "properties": properties, "geometry": geometry}


def test_metrics_preserve_geometry_properties_and_order_for_mixed_features():
    source = _collection(
        [
            _feature({"type": "Point", "coordinates": [1, 2]}, id="point"),
            _feature(
                {"type": "LineString", "coordinates": [[0, 0], [3, 4]]},
                id="line",
            ),
            _feature(
                {
                    "type": "Polygon",
                    "coordinates": [
                        [[0, 0], [10, 0], [10, 5], [0, 5], [0, 0]]
                    ],
                },
                id="polygon",
            ),
        ]
    )
    before = deepcopy(source)

    result = calculate_geometry_metrics(source)

    assert source == before
    assert result["starshine:crs"] == "EPSG:3857"
    assert [feature["properties"]["id"] for feature in result["features"]] == [
        "point",
        "line",
        "polygon",
    ]
    assert [
        feature["properties"]["geometry_area"] for feature in result["features"]
    ] == [0.0, 0.0, 50.0]
    assert [
        feature["properties"]["geometry_length"] for feature in result["features"]
    ] == [0.0, 5.0, 30.0]
    assert all(
        shape(result_feature["geometry"]).equals(shape(source_feature["geometry"]))
        for result_feature, source_feature in zip(
            result["features"], source["features"], strict=True
        )
    )


def test_metrics_support_custom_fields_and_empty_collections():
    empty = _collection([])
    assert calculate_geometry_metrics(
        empty,
        area_field="area_m2",
        length_field="length_m",
    ) == {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:3857",
        "features": [],
    }


def test_metrics_require_declared_projected_crs():
    feature = _feature({"type": "Point", "coordinates": [0, 0]}, id="p")
    with pytest.raises(ValidationError, match="declare starshine:crs"):
        calculate_geometry_metrics(_collection([feature], crs=None))
    with pytest.raises(ValidationError, match="projected CRS"):
        calculate_geometry_metrics(_collection([feature], crs="EPSG:4326"))


@pytest.mark.parametrize(
    ("area_field", "length_field", "message"),
    [
        ("", "length", "area_field"),
        ("area", " ", "length_field"),
        ("same", "same", "must be different"),
    ],
)
def test_metrics_reject_invalid_output_field_names(
    area_field,
    length_field,
    message,
):
    with pytest.raises(ValidationError, match=message):
        calculate_geometry_metrics(
            _collection([]),
            area_field=area_field,
            length_field=length_field,
        )


def test_metrics_reject_existing_output_properties():
    source = _collection(
        [
            _feature(
                {"type": "Point", "coordinates": [0, 0]},
                geometry_area=1,
            )
        ]
    )
    with pytest.raises(ValidationError, match="already contains geometry metric property"):
        calculate_geometry_metrics(source)


def test_metrics_workflow_and_planner_share_registry_defaults():
    source = _collection(
        [
            _feature(
                {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [2, 0], [2, 3], [0, 3], [0, 0]]],
                },
                id="p",
            )
        ]
    )
    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "geometry_metrics",
                "inputs": {"input": "features"},
                "parameters": {},
                "output": "measured",
            }
        ],
    }

    result = run_workflow(workflow, {"features": source})
    assert result["measured"]["features"][0]["properties"] == {
        "id": "p",
        "geometry_area": 6.0,
        "geometry_length": 10.0,
    }

    plan = plan_workflow(workflow, {"features", "unused"})
    assert plan["steps"][0]["parameters"] == {
        "area_field": "geometry_area",
        "length_field": "geometry_length",
    }
    assert plan["steps"][0]["parameter_sources"] == {
        "area_field": "default",
        "length_field": "default",
    }
    assert plan["unused_external_layers"] == ["unused"]


def test_metrics_workflow_unexpected_parameter_diagnostic_is_stable():
    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "geometry_metrics",
                "inputs": {"input": "features"},
                "parameters": {"units": "meters"},
                "output": "measured",
            }
        ],
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        plan_workflow(workflow, {"features"})

    assert exc_info.value.diagnostic.as_dict() == {
        "code": "unexpected_parameter",
        "message": "unexpected parameter for geometry_metrics: units",
        "path": "steps[0].parameters.units",
        "step_index": 0,
        "operation": "geometry_metrics",
    }
