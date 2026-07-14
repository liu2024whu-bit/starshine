import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import starshine_geo.workflow as workflow_module
from starshine_geo import WORKFLOW_PLAN_VERSION, digest_json, plan_workflow
from starshine_geo.cli import main
from starshine_geo.errors import WorkflowValidationError
from starshine_geo.operator_registry import ParameterSpec

ROOT = Path(__file__).resolve().parents[1]
PLAN_SCHEMA_PATH = ROOT / "schemas" / "workflow-plan-v1.schema.json"
PLAN_WORKFLOW_PATH = ROOT / "examples" / "plan.workflow.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _buffer_dissolve_workflow():
    return {
        "version": 1,
        "steps": [
            {
                "operation": "buffer",
                "inputs": {"input": "sites"},
                "parameters": {
                    "distance": 10,
                    "source_crs": "EPSG:3857",
                    "work_crs": "EPSG:3857",
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
    }


def test_workflow_plan_schema_is_valid_and_report_conforms():
    schema = _load(PLAN_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    report = plan_workflow(_load(PLAN_WORKFLOW_PATH), {"source", "mask", "unused"})
    Draft202012Validator(schema).validate(report)


def test_plan_resolves_registry_defaults_and_dependencies():
    report = plan_workflow(_buffer_dissolve_workflow(), {"sites", "unused"})

    assert report["schema_version"] == WORKFLOW_PLAN_VERSION
    assert report["declared_external_layers"] == ["sites", "unused"]
    assert report["required_external_layers"] == ["sites"]
    assert report["unused_external_layers"] == ["unused"]
    assert report["produced_layers"] == ["buffers", "coverage"]
    assert report["terminal_layers"] == ["coverage"]
    assert report["step_count"] == 2

    first, second = report["steps"]
    assert first["depends_on"] == []
    assert first["input_sources"] == {
        "input": {"kind": "external", "layer": "sites"}
    }
    assert first["parameters"]["segments"] == 16
    assert first["parameter_sources"] == {
        "distance": "provided",
        "source_crs": "provided",
        "work_crs": "provided",
        "segments": "default",
    }

    assert second["depends_on"] == [0]
    assert second["input_sources"] == {
        "input": {"kind": "step", "layer": "buffers", "step_index": 0}
    }
    assert second["parameters"] == {"group_field": None}
    assert second["parameter_sources"] == {"group_field": "default"}


def test_plan_is_deterministic_and_digest_covers_report_body():
    workflow = _load(PLAN_WORKFLOW_PATH)
    first = plan_workflow(workflow, ["source", "mask", "unused"])
    second = plan_workflow(deepcopy(workflow), ["unused", "mask", "source"])

    assert first == second
    body = deepcopy(first)
    digest = body.pop("plan_digest")
    assert digest == digest_json(body)


def test_plan_never_executes_registered_operators(monkeypatch):
    def unexpected_execution(inputs, parameters):
        raise AssertionError((inputs, parameters))

    monkeypatch.setitem(workflow_module.OPERATORS, "buffer", unexpected_execution)
    report = plan_workflow(_buffer_dissolve_workflow(), {"sites"})
    assert report["step_count"] == 2


def test_plan_reuses_stable_workflow_diagnostics():
    workflow = _buffer_dissolve_workflow()
    del workflow["steps"][0]["parameters"]["work_crs"]

    with pytest.raises(WorkflowValidationError) as exc_info:
        plan_workflow(workflow, {"sites"})

    assert exc_info.value.diagnostic.as_dict() == {
        "code": "missing_parameter",
        "message": "missing required parameter for buffer: work_crs",
        "path": "steps[0].parameters.work_crs",
        "step_index": 0,
        "operation": "buffer",
    }


def test_plan_command_prints_and_writes_the_same_report(tmp_path, capsys):
    expected = plan_workflow(_load(PLAN_WORKFLOW_PATH), {"source", "mask"})

    result = main(
        [
            "plan",
            str(PLAN_WORKFLOW_PATH),
            "--layer-name",
            "source",
            "--layer-name",
            "mask",
        ]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert json.loads(captured.out) == expected
    assert captured.err == ""

    destination = tmp_path / "workflow.plan.json"
    result = main(
        [
            "plan",
            str(PLAN_WORKFLOW_PATH),
            "--layer-name",
            "source",
            "--layer-name",
            "mask",
            "--output",
            str(destination),
        ]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert captured.out.strip() == str(destination)
    assert captured.err == ""
    assert _load(destination) == expected


def test_plan_command_refuses_to_overwrite_workflow(tmp_path, capsys):
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(PLAN_WORKFLOW_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    result = main(
        [
            "plan",
            str(workflow_path),
            "--layer-name",
            "source",
            "--layer-name",
            "mask",
            "--output",
            str(workflow_path),
            "--diagnostic-format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    assert result == 2
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "error": "starshine_error",
        "message": "workflow plan output must not overwrite the workflow file",
    }


def test_sensitive_registry_parameter_is_redacted_in_public_plans():
    parameter = ParameterSpec(
        "credential",
        "Synthetic sensitive value used only to test the public planning boundary.",
        {"type": "string"},
        lambda value: None,
        sensitive=True,
    )

    assert parameter.public_value("not-a-real-secret") == "<redacted>"
    assert parameter.as_dict()["sensitive"] is True
