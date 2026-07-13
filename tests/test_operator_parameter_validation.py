import pytest

import starshine_geo.workflow as workflow_module
from starshine_geo.errors import WorkflowValidationError
from starshine_geo.workflow import run_workflow, validate_workflow


BUFFER_LAYER = {
    "type": "FeatureCollection",
    "starshine:crs": "EPSG:4326",
    "features": [
        {
            "type": "Feature",
            "properties": {"id": "site-a"},
            "geometry": {"type": "Point", "coordinates": [114.3, 30.5]},
        }
    ],
}


def _buffer_step(parameters):
    return {
        "version": 1,
        "steps": [
            {
                "operation": "buffer",
                "inputs": {"input": "source"},
                "parameters": parameters,
                "output": "buffered",
            }
        ],
    }


def test_buffer_requires_all_semantic_parameters():
    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_workflow(
            _buffer_step({"distance": 100, "source_crs": "EPSG:4326"}),
            {"source"},
        )

    assert exc_info.value.diagnostic.as_dict() == {
        "code": "missing_parameter",
        "message": "missing required parameter for buffer: work_crs",
        "path": "steps[0].parameters.work_crs",
        "step_index": 0,
        "operation": "buffer",
    }


def test_buffer_rejects_geographic_work_crs_before_execution():
    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_workflow(
            _buffer_step(
                {
                    "distance": 100,
                    "source_crs": "EPSG:4326",
                    "work_crs": "EPSG:4326",
                }
            ),
            {"source"},
        )

    diagnostic = exc_info.value.diagnostic.as_dict()
    assert diagnostic["code"] == "invalid_parameter"
    assert diagnostic["path"] == "steps[0].parameters.work_crs"
    assert "projected CRS" in diagnostic["message"]


def test_unexpected_parameter_has_parameter_path():
    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_workflow(
            _buffer_step(
                {
                    "distance": 100,
                    "source_crs": "EPSG:4326",
                    "work_crs": "EPSG:3857",
                    "unsafe_mode": True,
                }
            ),
            {"source"},
        )

    assert exc_info.value.diagnostic.as_dict() == {
        "code": "unexpected_parameter",
        "message": "unexpected parameter for buffer: unsafe_mode",
        "path": "steps[0].parameters.unsafe_mode",
        "step_index": 0,
        "operation": "buffer",
    }


def test_unexpected_operator_input_is_rejected():
    workflow = _buffer_step(
        {
            "distance": 100,
            "source_crs": "EPSG:4326",
            "work_crs": "EPSG:3857",
        }
    )
    workflow["steps"][0]["inputs"]["points"] = "source"

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_workflow(workflow, {"source"})

    assert exc_info.value.diagnostic.path == "steps[0].inputs.points"
    assert exc_info.value.diagnostic.code == "unexpected_input"


def test_parameter_preflight_finishes_before_first_operator(monkeypatch):
    calls = []

    def unexpected_execution(context, step):
        calls.append((context, step))
        raise AssertionError("operator must not execute before parameter preflight completes")

    monkeypatch.setitem(workflow_module.OPERATORS, "buffer", unexpected_execution)

    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "buffer",
                "inputs": {"input": "source"},
                "parameters": {
                    "distance": 100,
                    "source_crs": "EPSG:4326",
                    "work_crs": "EPSG:3857",
                },
                "output": "first_buffer",
            },
            {
                "operation": "buffer",
                "inputs": {"input": "first_buffer"},
                "parameters": {
                    "distance": 0,
                    "source_crs": "EPSG:4326",
                    "work_crs": "EPSG:3857",
                },
                "output": "second_buffer",
            },
        ],
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        run_workflow(workflow, {"source": BUFFER_LAYER})

    assert exc_info.value.diagnostic.path == "steps[1].parameters.distance"
    assert calls == []
