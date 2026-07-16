from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from .errors import ValidationError
from .manifest import digest_json
from .planning import plan_workflow

WORKFLOW_GRAPH_VERSION = 1
WorkflowGraph = dict[str, Any]


def build_workflow_graph(
    workflow: dict[str, Any],
    layer_names: Iterable[str],
) -> WorkflowGraph:
    """Build a deterministic data-free graph from the canonical workflow plan.

    The graph contains layer and operation metadata only. It deliberately excludes parameter values,
    feature content, file paths, and credentials. Validation, dependency ordering, default
    resolution,
    and layer provenance remain single-sourced in :func:`plan_workflow`.
    """
    plan = plan_workflow(workflow, layer_names)
    required_external = set(plan["required_external_layers"])
    unused_external = set(plan["unused_external_layers"])
    terminal_layers = set(plan["terminal_layers"])

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    external_node_by_layer: dict[str, str] = {}
    produced_node_by_layer: dict[str, str] = {}

    for index, layer in enumerate(plan["declared_external_layers"]):
        node_id = f"external-{index}"
        external_node_by_layer[layer] = node_id
        nodes.append(
            {
                "id": node_id,
                "kind": "external_layer",
                "label": layer,
                "layer": layer,
                "required": layer in required_external,
                "unused": layer in unused_external,
            }
        )

    for step in plan["steps"]:
        step_index = step["index"]
        operation_node_id = f"step-{step_index}"
        output_node_id = f"layer-{step_index}"
        produced_node_by_layer[step["output"]] = output_node_id
        nodes.append(
            {
                "id": operation_node_id,
                "kind": "operation",
                "label": step["operation"],
                "step_index": step_index,
                "operation": step["operation"],
                "deterministic": step["deterministic"],
                "output_crs": step["output_crs"],
            }
        )
        nodes.append(
            {
                "id": output_node_id,
                "kind": "produced_layer",
                "label": step["output"],
                "layer": step["output"],
                "producer_step": step_index,
                "terminal": step["output"] in terminal_layers,
            }
        )

    for step in plan["steps"]:
        operation_node_id = f"step-{step['index']}"
        for input_name, source in step["input_sources"].items():
            layer = source["layer"]
            if source["kind"] == "external":
                source_node_id = external_node_by_layer[layer]
            else:
                source_node_id = produced_node_by_layer[layer]
            edges.append(
                {
                    "id": f"edge-{len(edges)}",
                    "kind": "input",
                    "source": source_node_id,
                    "target": operation_node_id,
                    "label": input_name,
                    "input_name": input_name,
                    "layer": layer,
                }
            )

        output_layer = step["output"]
        edges.append(
            {
                "id": f"edge-{len(edges)}",
                "kind": "output",
                "source": operation_node_id,
                "target": produced_node_by_layer[output_layer],
                "label": "output",
                "layer": output_layer,
            }
        )

    graph: WorkflowGraph = {
        "schema_version": WORKFLOW_GRAPH_VERSION,
        "workflow_version": plan["workflow_version"],
        "workflow_digest": plan["workflow_digest"],
        "operator_catalog_version": plan["operator_catalog_version"],
        "operator_catalog_digest": plan["operator_catalog_digest"],
        "plan_digest": plan["plan_digest"],
        "declared_external_layers": deepcopy(plan["declared_external_layers"]),
        "required_external_layers": deepcopy(plan["required_external_layers"]),
        "unused_external_layers": deepcopy(plan["unused_external_layers"]),
        "produced_layers": deepcopy(plan["produced_layers"]),
        "terminal_layers": deepcopy(plan["terminal_layers"]),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }
    graph["graph_digest"] = digest_json(graph)
    return graph


def _escape_mermaid_label(value: str) -> str:
    text = " ".join(value.splitlines())
    return (
        text.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "&#124;")
    )


def _validate_graph_for_render(
    graph: WorkflowGraph,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(graph, dict) or graph.get("schema_version") != WORKFLOW_GRAPH_VERSION:
        raise ValidationError("workflow graph must use schema version 1")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValidationError("workflow graph must contain node and edge arrays")

    node_ids: set[str] = set()
    supported_node_kinds = {"external_layer", "operation", "produced_layer"}
    for node in nodes:
        if not isinstance(node, dict):
            raise ValidationError("workflow graph nodes must be objects")
        node_id = node.get("id")
        label = node.get("label")
        kind = node.get("kind")
        if not isinstance(node_id, str) or not node_id or node_id in node_ids:
            raise ValidationError(
                "workflow graph node identifiers must be unique non-empty strings"
            )
        if not isinstance(label, str) or not isinstance(kind, str):
            raise ValidationError("workflow graph nodes must contain string kind and label values")
        if kind not in supported_node_kinds:
            raise ValidationError(f"unsupported workflow graph node kind: {kind}")
        node_ids.add(node_id)

    edge_ids: set[str] = set()
    for edge in edges:
        if not isinstance(edge, dict):
            raise ValidationError("workflow graph edges must be objects")
        edge_id = edge.get("id")
        if not isinstance(edge_id, str) or not edge_id or edge_id in edge_ids:
            raise ValidationError(
                "workflow graph edge identifiers must be unique non-empty strings"
            )
        if edge.get("kind") not in {"input", "output"}:
            raise ValidationError("workflow graph edges must use input or output kinds")
        if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
            raise ValidationError("workflow graph edges must reference existing nodes")
        if not isinstance(edge.get("label"), str):
            raise ValidationError("workflow graph edge labels must be strings")
        edge_ids.add(edge_id)
    return nodes, edges


def render_workflow_mermaid(graph: WorkflowGraph) -> str:
    """Render a graph as deterministic Mermaid flowchart text without data or parameter values."""
    nodes, edges = _validate_graph_for_render(graph)
    lines = ["flowchart LR"]
    for node in nodes:
        node_id = node["id"].replace("-", "_")
        label = _escape_mermaid_label(node["label"])
        if node["kind"] == "external_layer":
            prefix = "Unused external" if node.get("unused") else "External layer"
            lines.append(f'    {node_id}["{prefix}: {label}"]')
        elif node["kind"] == "operation":
            lines.append(
                f'    {node_id}{{{{"Step {node["step_index"]}: {label}"}}}}'
            )
        elif node["kind"] == "produced_layer":
            prefix = "Terminal layer" if node.get("terminal") else "Produced layer"
            lines.append(f'    {node_id}["{prefix}: {label}"]')
        else:
            raise ValidationError(f"unsupported workflow graph node kind: {node['kind']}")

    for edge in edges:
        source = edge["source"].replace("-", "_")
        target = edge["target"].replace("-", "_")
        label = _escape_mermaid_label(edge["label"])
        lines.append(f'    {source} -->|"{label}"| {target}')
    return "\n".join(lines) + "\n"


__all__ = [
    "WORKFLOW_GRAPH_VERSION",
    "WorkflowGraph",
    "build_workflow_graph",
    "render_workflow_mermaid",
]
