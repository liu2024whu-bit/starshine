import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from starshine_geo import (
    WORKFLOW_GRAPH_VERSION,
    build_workflow_graph,
    digest_json,
    render_workflow_mermaid,
)
from starshine_geo.cli import main

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "examples" / "plan.workflow.json"
SCHEMA = ROOT / "schemas" / "workflow-graph-v1.schema.json"


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_graph_schema_and_deterministic_model():
    schema = _load(SCHEMA)
    Draft202012Validator.check_schema(schema)
    first = build_workflow_graph(_load(WORKFLOW), {"source", "mask", "unused"})
    second = build_workflow_graph(deepcopy(_load(WORKFLOW)), ["unused", "mask", "source"])
    assert first == second
    Draft202012Validator(schema).validate(first)
    assert first["schema_version"] == WORKFLOW_GRAPH_VERSION
    assert first["node_count"] == len(first["nodes"])
    assert first["edge_count"] == len(first["edges"])
    body = deepcopy(first)
    digest = body.pop("graph_digest")
    assert digest == digest_json(body)


def test_graph_exposes_layers_steps_and_named_inputs():
    graph = build_workflow_graph(_load(WORKFLOW), {"source", "mask"})
    assert [node["id"] for node in graph["nodes"]] == [
        "layer:mask", "layer:source", "step:0", "layer:projected",
        "step:1", "layer:clipped", "step:2", "layer:coverage",
    ]
    assert graph["nodes"][-1]["terminal"] is True
    assert graph["edges"][0] == {
        "source": "layer:source", "target": "step:0", "kind": "input",
        "input": "input", "layer": "source",
    }


def test_mermaid_is_stable_and_human_readable():
    graph = build_workflow_graph(_load(WORKFLOW), {"source", "mask"})
    rendered = render_workflow_mermaid(graph)
    assert rendered.startswith("flowchart LR\n")
    assert '0: reproject' in rendered
    assert 'coverage (terminal)' in rendered
    assert '-->|"mask"|' in rendered
    assert rendered == render_workflow_mermaid(deepcopy(graph))


def test_graph_cli_prints_json_and_mermaid(tmp_path, capsys):
    args = ["graph", str(WORKFLOW), "--layer-name", "source", "--layer-name", "mask"]
    assert main(args) == 0
    graph = json.loads(capsys.readouterr().out)
    assert graph == build_workflow_graph(_load(WORKFLOW), {"source", "mask"})

    output = tmp_path / "workflow.mmd"
    assert main(args + ["--format", "mermaid", "--output", str(output)]) == 0
    assert capsys.readouterr().out.strip() == str(output)
    assert output.read_text(encoding="utf-8") == render_workflow_mermaid(graph)


def test_graph_cli_refuses_to_overwrite_workflow(tmp_path, capsys):
    workflow = tmp_path / "workflow.json"
    workflow.write_text(WORKFLOW.read_text(encoding="utf-8"), encoding="utf-8")
    result = main([
        "graph", str(workflow), "--layer-name", "source", "--layer-name", "mask",
        "--output", str(workflow), "--diagnostic-format", "json",
    ])
    captured = capsys.readouterr()
    assert result == 2
    assert json.loads(captured.err)["message"] == "workflow graph output must not overwrite the workflow file"
