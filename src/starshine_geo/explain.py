from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Iterable

from .errors import ValidationError
from .graph import _build_workflow_graph_from_plan
from .manifest import digest_json
from .planning import plan_workflow

WORKFLOW_EXPLANATION_VERSION = 1
WorkflowExplanation = dict[str, Any]

_REMAINING_CHECKS = (
    "Loaded collections must satisfy their declared CRS and geometry contracts.",
    "Required properties, identifier uniqueness, and output-field collisions are checked with data.",
    "Spatial relationships, distances, and empty-result behavior depend on actual feature content.",
    "Post-execution output and manifest digests require running the workflow.",
)


def explain_workflow(
    workflow: dict[str, Any],
    layer_names: Iterable[str],
) -> WorkflowExplanation:
    """Build a deterministic data-free explanation from the canonical workflow plan and graph.

    The explanation includes registry-resolved parameter values already redacted by the planner,
    direct dependencies, input provenance, terminal outputs, and execution-time limitations. It does
    not read feature data, open external datasets, or execute spatial operators.
    """
    plan = plan_workflow(workflow, layer_names)
    graph = _build_workflow_graph_from_plan(plan)
    terminal_layers = set(plan["terminal_layers"])

    steps: list[dict[str, Any]] = []
    for step in plan["steps"]:
        inputs = []
        for name, source in step["input_sources"].items():
            item: dict[str, Any] = {
                "name": name,
                "layer": source["layer"],
                "source_kind": source["kind"],
            }
            if source["kind"] == "step":
                item["producer_step"] = source["step_index"]
            inputs.append(item)

        parameters = [
            {
                "name": name,
                "value": deepcopy(value),
                "source": step["parameter_sources"][name],
            }
            for name, value in step["parameters"].items()
        ]

        steps.append(
            {
                "index": step["index"],
                "operation": step["operation"],
                "summary": step["summary"],
                "deterministic": step["deterministic"],
                "dependencies": deepcopy(step["depends_on"]),
                "inputs": inputs,
                "parameters": parameters,
                "output": step["output"],
                "output_crs": step["output_crs"],
                "terminal": step["output"] in terminal_layers,
            }
        )

    explanation: WorkflowExplanation = {
        "schema_version": WORKFLOW_EXPLANATION_VERSION,
        "workflow_version": plan["workflow_version"],
        "workflow_digest": plan["workflow_digest"],
        "operator_catalog_version": plan["operator_catalog_version"],
        "operator_catalog_digest": plan["operator_catalog_digest"],
        "plan_digest": plan["plan_digest"],
        "graph_digest": graph["graph_digest"],
        "declared_external_layers": deepcopy(plan["declared_external_layers"]),
        "required_external_layers": deepcopy(plan["required_external_layers"]),
        "unused_external_layers": deepcopy(plan["unused_external_layers"]),
        "produced_layers": deepcopy(plan["produced_layers"]),
        "terminal_layers": deepcopy(plan["terminal_layers"]),
        "step_count": plan["step_count"],
        "all_steps_deterministic": all(step["deterministic"] for step in plan["steps"]),
        "steps": steps,
        "remaining_checks": list(_REMAINING_CHECKS),
    }
    explanation["explanation_digest"] = digest_json(explanation)
    return explanation


def _inline_code(value: Any, *, quote_strings: bool = True) -> str:
    if isinstance(value, str) and not quote_strings:
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    text = " ".join(text.splitlines()).replace("`", "\\`")
    return f"`{text}`"


def _validate_explanation_for_render(explanation: WorkflowExplanation) -> list[dict[str, Any]]:
    if not isinstance(explanation, dict) or explanation.get("schema_version") != 1:
        raise ValidationError("workflow explanation must use schema version 1")
    steps = explanation.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValidationError("workflow explanation must contain a non-empty steps array")
    for step in steps:
        if not isinstance(step, dict):
            raise ValidationError("workflow explanation steps must be objects")
        if not isinstance(step.get("index"), int) or not isinstance(step.get("operation"), str):
            raise ValidationError("workflow explanation steps require index and operation values")
        if not isinstance(step.get("inputs"), list) or not isinstance(step.get("parameters"), list):
            raise ValidationError("workflow explanation steps require input and parameter arrays")
    return steps


def render_workflow_explanation_markdown(explanation: WorkflowExplanation) -> str:
    """Render a deterministic Markdown explanation without feature data or file paths."""
    steps = _validate_explanation_for_render(explanation)

    def layer_list(name: str) -> str:
        values = explanation.get(name, [])
        if not values:
            return "none"
        return ", ".join(_inline_code(value, quote_strings=False) for value in values)

    lines = [
        "# Starshine Workflow Explanation",
        "",
        f"- Workflow version: {_inline_code(explanation['workflow_version'])}",
        f"- Steps: {explanation['step_count']}",
        f"- Required external layers: {layer_list('required_external_layers')}",
        f"- Unused external layers: {layer_list('unused_external_layers')}",
        f"- Terminal layers: {layer_list('terminal_layers')}",
        "- All steps deterministic: "
        + ("yes" if explanation.get("all_steps_deterministic") else "no"),
        "",
    ]

    for step in steps:
        lines.extend(
            [
                f"## Step {step['index']}: {_inline_code(step['operation'], quote_strings=False)}",
                "",
                str(step["summary"]),
                "",
                "### Inputs",
                "",
            ]
        )
        for item in step["inputs"]:
            if item["source_kind"] == "external":
                source = f"external layer {_inline_code(item['layer'], quote_strings=False)}"
            else:
                source = (
                    f"layer {_inline_code(item['layer'], quote_strings=False)} produced by step "
                    f"{item['producer_step']}"
                )
            lines.append(f"- {_inline_code(item['name'], quote_strings=False)}: {source}")

        lines.extend(["", "### Parameters", ""])
        if step["parameters"]:
            for parameter in step["parameters"]:
                lines.append(
                    f"- {_inline_code(parameter['name'], quote_strings=False)} = "
                    f"{_inline_code(parameter['value'])} ({parameter['source']})"
                )
        else:
            lines.append("- none")

        dependencies = step["dependencies"]
        dependency_text = "none" if not dependencies else ", ".join(map(str, dependencies))
        lines.extend(
            [
                "",
                f"- Direct dependencies: {dependency_text}",
                f"- Output layer: {_inline_code(step['output'], quote_strings=False)}",
                f"- Output CRS behavior: {step['output_crs']}",
                "- Deterministic: " + ("yes" if step["deterministic"] else "no"),
                "- Terminal output: " + ("yes" if step["terminal"] else "no"),
                "",
            ]
        )

    lines.extend(["## Remaining execution-time checks", ""])
    for message in explanation.get("remaining_checks", []):
        lines.append(f"- {message}")

    lines.extend(
        [
            "",
            "## Evidence",
            "",
            f"- Workflow digest: {_inline_code(explanation['workflow_digest'], quote_strings=False)}",
            f"- Plan digest: {_inline_code(explanation['plan_digest'], quote_strings=False)}",
            f"- Graph digest: {_inline_code(explanation['graph_digest'], quote_strings=False)}",
            f"- Explanation digest: {_inline_code(explanation['explanation_digest'], quote_strings=False)}",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "WORKFLOW_EXPLANATION_VERSION",
    "WorkflowExplanation",
    "explain_workflow",
    "render_workflow_explanation_markdown",
]
