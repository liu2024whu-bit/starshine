import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import starshine_geo.workflow as workflow_module
from starshine_geo import (
    WORKFLOW_GRAPH_VERSION,
    build_workflow_graph,
    digest_json,
    render_workflow_mermaid,
)
from starshine_geo.cli import main
from starshine_geo.errors import ValidationError, WorkflowValidationError

ROOT = Path(__file__).resolve().parents[1]
GRAPH_SCHEMA_PATH = ROOT / "schemas" / "workflow-graph-v1.schema.json"
PLAN_WORKFLOW_PATH = ROOT / "examples" / "plan.workflow.json"
MERMAID_EXAMPLE_PATH = ROOT / "examples" / "plan.workflow.mmd"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _buffer_workflow(layer_name="sites"):
    return {
        "version": 1,
        "steps": [
            {
                "operation": "buffer",
                "inputs": {"input": layer_name},
                "parameters": {
                    "distance": 10,
                    "source_crs": "EPSG:3857",
                    "work_crs": "EPSG:3857",
                },
                "output": "buffers",
            }
        ],
    }


def test_workflow_graph_schema_is_valid_and_report_conforms():
    schema = _load(GRAPH_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    graph = build_workflow_graph(_load(PLAN_WORKFLOW_PATH), {"source", "mask", "unused"})
    Draft202012Validator(schema).validate(graph)


def test_graph_is_derived_from_plan_with_stable_nodes_and_edges():
    graph = build_workflow_graph(_load(PLAN_WORKFLOW_PATH), {"source", "mask", "unused"})

    assert graph["schema_version"] == WORKFLOW_GRAPH_VERSION
    assert graph["declared_external_layers"] == ["mask", "source", "unused"]
    assert graph["required_external_layers"] == ["mask", "source"]
    assert graph["unused_external_layers"] == ["unused"]
    assert graph["produced_layers"] == ["projected", "clipped", "coverage"]
    assert graph["terminal_layers"] == ["coverage"]
    assert graph["node_count"] == 9
    assert graph["edge_count"] == 7

    assert graph["nodes"] == [
        {
            "id": "external-0",
            "kind": "external_layer",
            "label": "mask",
            "layer": "mask",
            "required": True,
            "unused": False,
        },
        {
            "id": "external-1",
            "kind": "external_layer",
            "label": "source",
            "layer": "source",
            "required": True,
            "unused": False,
        },
        {
            "id": "external-2",
            "kind": "external_layer",
            "label": "unused",
            "layer": "unused",
            "required": False,
            "unused": True,
        },
        {
            "id": "step-0",
            "kind": "operation",
            "label": "reproject",
            "step_index": 0,
            "operation": "reproject",
            "deterministic": True,
            "output_crs": "target_crs parameter",
        },
        {
            "id": "layer-0",
            "kind": "produced_layer",
            "label": "projected",
            "layer": "projected",
            "producer_step": 0,
            "terminal": False,
        },
        {
            "id": "step-1",
            "kind": "operation",
            "label": "clip",
            "step_index": 1,
            "operation": "clip",
            "deterministic": True,
            "output_crs": "input layer; mask must declare an equivalent CRS",
        },
        {
            "id": "layer-1",
            "kind": "produced_layer",
            "label": "clipped",
            "layer": "clipped",
            "producer_step": 1,
            "terminal": False,
        },
        {
            "id": "step-2",
            "kind": "operation",
            "label": "dissolve",
            "step_index": 2,
            "operation": "dissolve",
            "deterministic": True,
            "output_crs": "input layer",
        },
        {
            "id": "layer-2",
            "kind": "produced_layer",
            "label": "coverage",
            "layer": "coverage",
            "producer_step": 2,
            "terminal": True,
        },
    ]
    assert graph["edges"] == [
        {
            "id": "edge-0",
            "kind": "input",
            "source": "external-1",
            "target": "step-0",
            "label": "input",
            "input_name": "input",
            "layer": "source",
        },
        {
            "id": "edge-1",
            "kind": "output",
            "source": "step-0",
            "target": "layer-0",
            "label": "output",
            "layer": "projected",
        },
        {
            "id": "edge-2",
            "kind": "input",
            "source": "layer-0",
            "target": "step-1",
            "label": "input",
            "input_name": "input",
            "layer": "projected",
        },
        {
            "id": "edge-3",
            "kind": "input",
            "source": "external-0",
            "target": "step-1",
            "label": "mask",
            "input_name": "mask",
            "layer": "mask",
        },
        {
            "id": "edge-4",
            "kind": "output",
            "source": "step-1",
            "target": "layer-1",
            "label": "output",
            "layer": "clipped",
        },
        {
            "id": "edge-5",
            "kind": "input",
            "source": "layer-1",
            "target": "step-2",
            "label": "input",
            "input_name": "input",
            "layer": "clipped",
        },
        {
            "id": "edge-6",
            "kind": "output",
            "source": "step-2",
            "target": "layer-2",
            "label": "output",
            "layer": "coverage",
        },
    ]


def test_graph_is_deterministic_and_digest_covers_report_body():
    workflow = _load(PLAN_WORKFLOW_PATH)
    first = build_workflow_graph(workflow, ["source", "mask", "unused"])
    second = build_workflow_graph(deepcopy(workflow), ["unused", "mask", "source"])

    assert first == second
    body = deepcopy(first)
    digest = body.pop("graph_digest")
    assert digest == digest_json(body)


def test_graph_never_executes_registered_operators(monkeypatch):
    def unexpected_execution(inputs, parameters):
        raise AssertionError((inputs, parameters))

    monkeypatch.setitem(workflow_module.OPERATORS, "buffer", unexpected_execution)
    graph = build_workflow_graph(_buffer_workflow(), {"sites"})
    assert graph["node_count"] == 3
    assert graph["edge_count"] == 2


def test_graph_excludes_parameters_paths_and_feature_data():
    graph = build_workflow_graph(_buffer_workflow(), {"sites"})
    serialized = json.dumps(graph, sort_keys=True)
    mermaid = render_workflow_mermaid(graph)

    assert "parameters" not in serialized
    assert "EPSG:3857" not in serialized
    assert '"distance": 10' not in serialized
    assert "EPSG:3857" not in mermaid
    assert "distance" not in mermaid


def test_mermaid_renderer_is_deterministic_escaped_and_matches_tracked_example():
    graph = build_workflow_graph(_load(PLAN_WORKFLOW_PATH), {"source", "mask", "unused"})
    mermaid = render_workflow_mermaid(graph)

    assert mermaid == MERMAID_EXAMPLE_PATH.read_text(encoding="utf-8")
    escaped_layer = 'source "<&| layer'
    escaped_graph = build_workflow_graph(_buffer_workflow(escaped_layer), {escaped_layer})
    escaped = render_workflow_mermaid(escaped_graph)
    assert "&quot;" in escaped
    assert "&lt;" in escaped
    assert "&amp;" in escaped
    assert "&#124;" in escaped


def test_mermaid_renderer_rejects_mutated_graph_references():
    graph = build_workflow_graph(_buffer_workflow(), {"sites"})
    graph["edges"][0]["source"] = "missing"

    with pytest.raises(ValidationError, match="reference existing nodes"):
        render_workflow_mermaid(graph)


def test_graph_reuses_stable_workflow_diagnostics():
    workflow = _buffer_workflow()
    del workflow["steps"][0]["parameters"]["work_crs"]

    with pytest.raises(WorkflowValidationError) as exc_info:
        build_workflow_graph(workflow, {"sites"})

    assert exc_info.value.diagnostic.as_dict() == {
        "code": "missing_parameter",
        "message": "missing required parameter for buffer: work_crs",
        "path": "steps[0].parameters.work_crs",
        "step_index": 0,
        "operation": "buffer",
    }


def test_graph_command_prints_and_writes_json_and_mermaid(tmp_path, capsys):
    expected_graph = build_workflow_graph(_load(PLAN_WORKFLOW_PATH), {"source", "mask"})
    expected_mermaid = render_workflow_mermaid(expected_graph)

    result = main(
        [
            "graph",
            str(PLAN_WORKFLOW_PATH),
            "--layer-name",
            "source",
            "--layer-name",
            "mask",
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert json.loads(captured.out) == expected_graph
    assert captured.err == ""

    result = main(
        [
            "graph",
            str(PLAN_WORKFLOW_PATH),
            "--layer-name",
            "source",
            "--layer-name",
            "mask",
        ]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert captured.out == expected_mermaid
    assert captured.err == ""

    json_destination = tmp_path / "workflow.graph.json"
    result = main(
        [
            "graph",
            str(PLAN_WORKFLOW_PATH),
            "--layer-name",
            "source",
            "--layer-name",
            "mask",
            "--format",
            "json",
            "--output",
            str(json_destination),
        ]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert captured.out.strip() == str(json_destination)
    assert _load(json_destination) == expected_graph

    mermaid_destination = tmp_path / "workflow.mmd"
    result = main(
        [
            "graph",
            str(PLAN_WORKFLOW_PATH),
            "--layer-name",
            "source",
            "--layer-name",
            "mask",
            "--output",
            str(mermaid_destination),
        ]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert captured.out.strip() == str(mermaid_destination)
    assert mermaid_destination.read_text(encoding="utf-8") == expected_mermaid


def test_graph_command_refuses_to_overwrite_workflow(tmp_path, capsys):
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(PLAN_WORKFLOW_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    result = main(
        [
            "graph",
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
        "message": "workflow graph output must not overwrite the workflow file",
    }
