import pytest

import starshine_geo.workflow as workflow_module
from starshine_geo.errors import (
    UnsupportedOperationError,
    ValidationError,
    WorkflowValidationError,
)
from starshine_geo.workflow import run_workflow, validate_workflow


LAYERS = {
    "zones": {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"id": "one"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
                },
            }
        ],
    },
    "sites": {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Point", "coordinates": [1, 1]},
            }
        ],
    },
}


def test_workflow_executes_registered_operator():
    result = run_workflow(
        {
            "version": 1,
            "steps": [
                {
                    "operation": "summarize_points_within",
                    "inputs": {"polygons": "zones", "points": "sites"},
                    "parameters": {},
                    "output": "summary",
                }
            ],
        },
        LAYERS,
    )
    assert result["summary"]["features"][0]["properties"]["point_count"] == 1


def test_workflow_rejects_dynamic_operation():
    with pytest.raises(UnsupportedOperationError) as exc_info:
        run_workflow(
            {"version": 1, "steps": [{"operation": "eval", "inputs": {}, "output": "x"}]},
            LAYERS,
        )

    assert exc_info.value.diagnostic.as_dict() == {
        "code": "unsupported_operation",
        "message": "unsupported operation: 'eval'",
        "path": "steps[0].operation",
        "step_index": 0,
        "operation": "eval",
    }


def test_workflow_does_not_overwrite_input_layers():
    with pytest.raises(ValidationError, match="overwrite"):
        run_workflow(
            {
                "version": 1,
                "steps": [
                    {
                        "operation": "summarize_points_within",
                        "inputs": {"polygons": "zones", "points": "sites"},
                        "output": "zones",
                    }
                ],
            },
            LAYERS,
        )


def test_unknown_input_has_stable_structured_diagnostic():
    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_workflow(
            {
                "version": 1,
                "steps": [
                    {
                        "operation": "summarize_points_within",
                        "inputs": {"polygons": "missing", "points": "sites"},
                        "output": "summary",
                    }
                ],
            },
            LAYERS,
        )

    assert exc_info.value.diagnostic.as_dict() == {
        "code": "unknown_input_layer",
        "message": "unknown input layer: missing",
        "path": "steps[0].inputs.polygons",
        "step_index": 0,
        "operation": "summarize_points_within",
    }


def test_complete_workflow_is_validated_before_first_operator(monkeypatch):
    calls = []

    def unexpected_execution(context, step):
        calls.append((context, step))
        raise AssertionError("operator should not execute before workflow validation completes")

    monkeypatch.setitem(
        workflow_module.OPERATORS,
        "summarize_points_within",
        unexpected_execution,
    )

    with pytest.raises(WorkflowValidationError, match="unknown input layer"):
        run_workflow(
            {
                "version": 1,
                "steps": [
                    {
                        "operation": "summarize_points_within",
                        "inputs": {"polygons": "zones", "points": "sites"},
                        "output": "first_summary",
                    },
                    {
                        "operation": "summarize_points_within",
                        "inputs": {"polygons": "missing", "points": "sites"},
                        "output": "second_summary",
                    },
                ],
            },
            LAYERS,
        )

    assert calls == []


def test_runtime_parameters_are_resolved_from_registry_defaults(monkeypatch):
    captured = {}

    def capture_defaults(inputs, parameters):
        captured.update(parameters)
        return inputs["input"]

    monkeypatch.setitem(workflow_module.OPERATORS, "dissolve", capture_defaults)
    result = run_workflow(
        {
            "version": 1,
            "steps": [
                {
                    "operation": "dissolve",
                    "inputs": {"input": "zones"},
                    "parameters": {},
                    "output": "coverage",
                }
            ],
        },
        LAYERS,
    )

    assert captured == {"group_field": None}
    assert result["coverage"] == LAYERS["zones"]
