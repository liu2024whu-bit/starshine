from __future__ import annotations

from typing import Any, Iterable

from .manifest import digest_json
from .planning import plan_workflow

WORKFLOW_GRAPH_VERSION = 1
WorkflowGraph = dict[str, Any]


def build_workflow_graph(workflow: dict[str, Any], layer_names: Iterable[str]) -> WorkflowGraph:
    """Build a deterministic bipartite data-flow graph from a validated workflow plan."""
    plan = plan_workflow(workflow, layer_names)
    terminal = set(plan["terminal_layers"])

    nodes: list[dict[str, Any]] = []
    for name in plan["declared_external_layers"]:
        if name in plan["required_external_layers"]:
            nodes.append(
                {
                    "id": f"layer:{name}",
                    "kind": "layer",
                    "name": name,
                    "provenance": "external",
                    "terminal": False,
                }
            )

    for step in plan["steps"]:
        nodes.append(
            {
                "id": f"step:{step['index']}",
                "kind": "step",
                "index": step["index"],
                "operation": step["operation"],
                "summary": step["summary"],
                "deterministic": step["deterministic"],
                "output_crs": step["output_crs"],
            }
        )
        output = step["output"]
        nodes.append(
            {
                "id": f"layer:{output}",
                "kind": "layer",
                "name": output,
                "provenance": "produced",
                "terminal": output in terminal,
            }
        )

    edges: list[dict[str, Any]] = []
    for step in plan["steps"]:
        step_id = f"step:{step['index']}"
        for input_name, layer_name in step["inputs"].items():
            edges.append(
                {
                    "source": f"layer:{layer_name}",
                    "target": step_id,
                    "kind": "input",
                    "input": input_name,
                    "layer": layer_name,
                }
            )
        edges.append(
            {
                "source": step_id,
                "target": f"layer:{step['output']}",
                "kind": "output",
                "layer": step["output"],
            }
        )

    graph: WorkflowGraph = {
        "schema_version": WORKFLOW_GRAPH_VERSION,
        "workflow_version": plan["workflow_version"],
        "workflow_digest": plan["workflow_digest"],
        "plan_digest": plan["plan_digest"],
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }
    graph["graph_digest"] = digest_json(graph)
    return graph


def _escape_mermaid_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def render_workflow_mermaid(graph: WorkflowGraph) -> str:
    """Render a deterministic left-to-right Mermaid flowchart from a workflow graph."""
    node_aliases = {node["id"]: f"N{index}" for index, node in enumerate(graph["nodes"])}
    lines = ["flowchart LR"]
    for node in graph["nodes"]:
        alias = node_aliases[node["id"]]
        if node["kind"] == "step":
            label = f"{node['index']}: {node['operation']}"
            lines.append(f'  {alias}["{_escape_mermaid_label(label)}"]')
        else:
            suffix = "terminal" if node["terminal"] else node["provenance"]
            label = f"{node['name']} ({suffix})"
            lines.append(f'  {alias}(["{_escape_mermaid_label(label)}"])')

    for edge in graph["edges"]:
        source = node_aliases[edge["source"]]
        target = node_aliases[edge["target"]]
        if edge["kind"] == "input":
            label = _escape_mermaid_label(edge["input"])
            lines.append(f'  {source} -->|"{label}"| {target}')
        else:
            lines.append(f"  {source} --> {target}")
    return "\n".join(lines) + "\n"


__all__ = [
    "WORKFLOW_GRAPH_VERSION",
    "WorkflowGraph",
    "build_workflow_graph",
    "render_workflow_mermaid",
]
