from __future__ import annotations

import json

import pytest

from starshine_geo.cli import main
from starshine_geo.errors import ValidationError, WorkflowValidationError
from starshine_geo.geojson import validate_feature_collection
from starshine_geo.operators import buffer_features, dissolve_features, nearest_features
from starshine_geo.workflow import run_workflow, validate_workflow


def layer(coordinates=(93, 0), properties=None):
    return {
        "type": "FeatureCollection", "starshine:crs": "EPSG:4326",
        "features": [{"type": "Feature", "properties": properties or {},
                      "geometry": {"type": "Point", "coordinates": coordinates}}],
    }


def workflow(distance=10):
    return {"version": 1, "steps": [{
        "operation": "buffer", "inputs": {"input": "source"}, "output": "result",
        "parameters": {"distance": distance, "source_crs": "EPSG:4326",
                       "work_crs": "EPSG:32631"},
    }]}


def test_buffer_rejects_failed_projection_instead_of_empty_output():
    with pytest.raises(ValidationError, match="transform|projection"):
        run_workflow(workflow(), {"source": layer()})


def test_buffer_normal_projection_remains_valid():
    result = run_workflow(workflow(), {"source": layer((3, 0))})["result"]
    assert len(validate_feature_collection(result)["features"]) == 1


@pytest.mark.parametrize("group", [["a"], {"a": 1}])
def test_dissolve_rejects_unhashable_group_without_typeerror(group):
    with pytest.raises(ValidationError, match="group"):
        dissolve_features(layer(properties={"group": group}), group_field="group")


@pytest.mark.parametrize("number", [10**400, -(10**400)])
def test_huge_workflow_distance_returns_parameter_diagnostic(number):
    with pytest.raises(WorkflowValidationError) as exc:
        validate_workflow(workflow(number), ["source"])
    assert exc.value.diagnostic.code == "invalid_parameter"
    assert exc.value.diagnostic.path == "steps[0].parameters.distance"


def test_huge_nearest_distance_returns_parameter_diagnostic():
    value = {"version": 1, "steps": [{
        "operation": "nearest", "inputs": {"source": "a", "candidates": "b"},
        "parameters": {"candidate_id_field": "id", "max_distance": 10**400},
        "output": "result",
    }]}
    with pytest.raises(WorkflowValidationError) as exc:
        validate_workflow(value, ["a", "b"])
    assert exc.value.diagnostic.code == "invalid_parameter"
    assert exc.value.diagnostic.path == "steps[0].parameters.max_distance"


def test_huge_distances_rejected_by_direct_apis():
    with pytest.raises(ValidationError):
        buffer_features(layer(), distance=10**400, source_crs="EPSG:4326",
                        work_crs="EPSG:32631")
    with pytest.raises(ValidationError):
        nearest_features(layer(), layer(), candidate_id_field="id", max_distance=10**400)


@pytest.mark.parametrize("case", ["projection", "huge", "group"])
def test_cli_core_failures_are_clean_and_do_not_write_result(tmp_path, capsys, case):
    value, source = workflow(), layer()
    if case == "huge":
        value = workflow(10**400)
    elif case == "group":
        source = layer(properties={"group": ["private-value"]})
        value["steps"][0] = {"operation": "dissolve", "inputs": {"input": "source"},
                              "parameters": {"group_field": "group"}, "output": "result"}
    workflow_path, input_path, output_path = [tmp_path / name for name in ("w", "i", "o")]
    workflow_path.write_text(json.dumps(value))
    input_path.write_text(json.dumps(source))
    assert main(["run", str(workflow_path), "--layer", f"source={input_path}",
                 "--output-layer", "result", "--output", str(output_path)]) == 2
    assert not output_path.exists()
    assert "private-value" not in capsys.readouterr().err


def test_failed_transform_rejects_reproject_too():
    from starshine_geo.operators import reproject_features

    with pytest.raises(ValidationError, match="transformation"):
        reproject_features(layer(), target_crs="EPSG:32631")


def test_empty_input_collection_remains_supported():
    source = layer()
    source["features"] = []
    assert run_workflow(workflow(), {"source": source})["result"]["features"] == []


def test_dissolve_missing_and_null_group_values_still_share_one_group():
    source = layer((0, 0))
    source["features"].extend(layer((1, 1), {"group": None})["features"])
    result = dissolve_features(source, group_field="group")
    assert len(result["features"]) == 1
    assert result["features"][0]["properties"] == {"group": None}


def test_failed_buffer_stops_multistep_execution(monkeypatch):
    import starshine_geo.workflow as workflow_module

    value = workflow()
    value["steps"].append({"operation": "dissolve", "inputs": {"input": "result"},
                           "output": "later"})

    def unexpected_execution(*args):
        raise AssertionError("downstream operator ran after a failed transformation")

    monkeypatch.setitem(workflow_module.OPERATORS, "dissolve", unexpected_execution)
    with pytest.raises(ValidationError, match="transformation"):
        run_workflow(value, {"source": layer()})


@pytest.mark.parametrize("segments", [True, False])
def test_direct_buffer_rejects_boolean_segments(segments):
    with pytest.raises(ValidationError, match="segments"):
        buffer_features(layer((3, 0)), distance=10, source_crs="EPSG:4326",
                        work_crs="EPSG:32631", segments=segments)


def test_huge_coordinate_is_already_a_validation_error():
    with pytest.raises(ValidationError, match="invalid geometry"):
        validate_feature_collection(layer((10**400, 0)))
