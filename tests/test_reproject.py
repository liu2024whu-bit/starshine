import pytest

from starshine_geo import reproject_features, run_workflow
from starshine_geo.errors import ValidationError, WorkflowValidationError
from starshine_geo.workflow import validate_workflow


WGS84_POINTS = {
    "type": "FeatureCollection",
    "starshine:crs": "EPSG:4326",
    "features": [
        {
            "type": "Feature",
            "properties": {"id": "origin", "rank": 1},
            "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
        },
        {
            "type": "Feature",
            "properties": {"id": "unit", "rank": 2},
            "geometry": {"type": "Point", "coordinates": [1.0, 1.0]},
        },
    ],
}


def test_reproject_uses_declared_source_crs_and_preserves_properties_and_order():
    result = reproject_features(WGS84_POINTS, target_crs="EPSG:3857")

    assert result["starshine:crs"] == "EPSG:3857"
    assert [feature["properties"] for feature in result["features"]] == [
        {"id": "origin", "rank": 1},
        {"id": "unit", "rank": 2},
    ]
    assert result["features"][0]["geometry"]["coordinates"] == pytest.approx((0.0, 0.0))
    assert result["features"][1]["geometry"]["coordinates"] == pytest.approx(
        (111319.49079327357, 111325.1428663851),
        rel=1e-9,
    )


def test_reproject_allows_explicit_source_for_unlabelled_collection():
    unlabelled = {key: value for key, value in WGS84_POINTS.items() if key != "starshine:crs"}
    result = reproject_features(
        unlabelled,
        source_crs="EPSG:4326",
        target_crs="EPSG:3857",
    )

    assert result["starshine:crs"] == "EPSG:3857"
    assert len(result["features"]) == 2


def test_reproject_requires_source_when_collection_is_unlabelled():
    unlabelled = {key: value for key, value in WGS84_POINTS.items() if key != "starshine:crs"}

    with pytest.raises(
        ValidationError,
        match="source_crs is required when the collection has no starshine:crs",
    ):
        reproject_features(unlabelled, target_crs="EPSG:3857")


def test_reproject_rejects_source_parameter_that_conflicts_with_declared_crs():
    with pytest.raises(
        ValidationError,
        match="source_crs does not match the collection starshine:crs",
    ):
        reproject_features(
            WGS84_POINTS,
            source_crs="EPSG:3857",
            target_crs="EPSG:32650",
        )


def test_reproject_handles_empty_valid_collection():
    result = reproject_features(
        {"type": "FeatureCollection", "starshine:crs": "EPSG:4326", "features": []},
        target_crs="EPSG:3857",
    )

    assert result == {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:3857",
        "features": [],
    }


def test_reproject_workflow_executes_through_registry():
    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "reproject",
                "inputs": {"input": "source"},
                "parameters": {"target_crs": "EPSG:3857"},
                "output": "projected",
            }
        ],
    }

    result = run_workflow(workflow, {"source": WGS84_POINTS})
    assert result["projected"]["starshine:crs"] == "EPSG:3857"
    assert len(result["projected"]["features"]) == 2


def test_reproject_missing_target_has_stable_preflight_diagnostic():
    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_workflow(
            {
                "version": 1,
                "steps": [
                    {
                        "operation": "reproject",
                        "inputs": {"input": "source"},
                        "parameters": {},
                        "output": "projected",
                    }
                ],
            },
            {"source"},
        )

    assert exc_info.value.diagnostic.as_dict() == {
        "code": "missing_parameter",
        "message": "missing required parameter for reproject: target_crs",
        "path": "steps[0].parameters.target_crs",
        "step_index": 0,
        "operation": "reproject",
    }


def test_reproject_rejects_invalid_target_crs_during_preflight():
    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_workflow(
            {
                "version": 1,
                "steps": [
                    {
                        "operation": "reproject",
                        "inputs": {"input": "source"},
                        "parameters": {"target_crs": "not-a-crs"},
                        "output": "projected",
                    }
                ],
            },
            {"source"},
        )

    assert exc_info.value.diagnostic.code == "invalid_parameter"
    assert exc_info.value.diagnostic.path == "steps[0].parameters.target_crs"
    assert "Invalid CRS" in exc_info.value.diagnostic.message
