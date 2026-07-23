from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from ._markdown import inline_code
from .contract_specs import InputContractSpec
from .errors import ValidationError
from .manifest import digest_json
from .operator_registry import OPERATOR_REGISTRY
from .planning import plan_workflow

WORKFLOW_CONTRACT_VERSION = 1
WorkflowContract = dict[str, Any]

_REMAINING_CHECKS = (
    "Feature geometry types and property values must be checked against each listed input use.",
    "Declared CRS values, CRS equivalence, and projected-coordinate requirements need loaded data.",
    "Field uniqueness, nullability, scalar constraints, and collision policies need loaded properties.",
    "Spatial relationships, distances, and output feature counts remain execution-time results.",
)


def _resolve_crs(
    contract: InputContractSpec,
    *,
    parameters: dict[str, Any],
    step_inputs: dict[str, str],
) -> dict[str, Any]:
    mode = contract.crs_mode
    result: dict[str, Any]
    if mode == "declared_or_parameter":
        value = parameters.get(contract.crs_parameter or "")
        if value is None:
            result = {"mode": "declared"}
        else:
            result = {
                "mode": "declared_or_parameter",
                "parameter": contract.crs_parameter,
                "value": deepcopy(value),
            }
    elif mode == "parameter":
        result = {
            "mode": "parameter",
            "parameter": contract.crs_parameter,
            "value": deepcopy(parameters.get(contract.crs_parameter or "")),
        }
    else:
        result = {"mode": mode}

    if contract.equivalent_crs_to is not None:
        result["equivalent_to_layer"] = step_inputs[contract.equivalent_crs_to]
    return result


def _resolve_input_use(
    *,
    step: dict[str, Any],
    input_name: str,
    contract: InputContractSpec,
) -> dict[str, Any]:
    parameters = step["parameters"]
    required_fields = []
    for requirement in contract.required_fields:
        resolved = requirement.resolve(parameters)
        if resolved is not None:
            required_fields.append(resolved)

    written_fields = []
    for write in contract.written_fields:
        resolved = write.resolve(parameters)
        if resolved is not None:
            written_fields.append(resolved)

    return {
        "step_index": step["index"],
        "operation": step["operation"],
        "input_name": input_name,
        "geometry_types": list(contract.geometry_types),
        "crs": _resolve_crs(
            contract,
            parameters=parameters,
            step_inputs=step["inputs"],
        ),
        "required_fields": required_fields,
        "written_fields": written_fields,
        "notes": list(contract.notes),
    }


def build_workflow_contract(
    workflow: dict[str, Any],
    layer_names: Iterable[str],
) -> WorkflowContract:
    """Build a deterministic data-preparation contract for external workflow layers.

    The report derives step ordering, defaults, redaction, and layer provenance from the canonical
    planner. Input geometry, CRS, field-read, and field-write rules come from declarative operator
    registry metadata. No feature collection is opened and no operator executes.
    """
    plan = plan_workflow(workflow, layer_names)
    required_layers = set(plan["required_external_layers"])
    unused_layers = set(plan["unused_external_layers"])
    uses_by_layer: dict[str, list[dict[str, Any]]] = {
        name: [] for name in plan["declared_external_layers"]
    }

    for step in plan["steps"]:
        spec = OPERATOR_REGISTRY[step["operation"]]
        by_name = {item.name: item for item in spec.inputs}
        for input_name, source in step["input_sources"].items():
            if source["kind"] != "external":
                continue
            uses_by_layer[source["layer"]].append(
                _resolve_input_use(
                    step=step,
                    input_name=input_name,
                    contract=by_name[input_name].contract,
                )
            )

    layers = [
        {
            "name": name,
            "required": name in required_layers,
            "unused": name in unused_layers,
            "use_count": len(uses_by_layer[name]),
            "uses": uses_by_layer[name],
        }
        for name in plan["declared_external_layers"]
    ]

    report: WorkflowContract = {
        "schema_version": WORKFLOW_CONTRACT_VERSION,
        "workflow_version": plan["workflow_version"],
        "workflow_digest": plan["workflow_digest"],
        "operator_catalog_version": plan["operator_catalog_version"],
        "operator_catalog_digest": plan["operator_catalog_digest"],
        "plan_digest": plan["plan_digest"],
        "declared_external_layers": deepcopy(plan["declared_external_layers"]),
        "required_external_layers": deepcopy(plan["required_external_layers"]),
        "unused_external_layers": deepcopy(plan["unused_external_layers"]),
        "layer_count": len(layers),
        "layers": layers,
        "remaining_checks": list(_REMAINING_CHECKS),
    }
    report["contract_digest"] = digest_json(report)
    return report


def _validate_contract_for_render(contract: WorkflowContract) -> list[dict[str, Any]]:
    if not isinstance(contract, dict) or contract.get("schema_version") != 1:
        raise ValidationError("workflow contract must use schema version 1")
    layers = contract.get("layers")
    if not isinstance(layers, list):
        raise ValidationError("workflow contract must contain a layers array")
    for layer in layers:
        if not isinstance(layer, dict) or not isinstance(layer.get("name"), str):
            raise ValidationError("workflow contract layers require string names")
        if not isinstance(layer.get("uses"), list):
            raise ValidationError("workflow contract layers require uses arrays")
    return layers


def _crs_text(crs: dict[str, Any]) -> str:
    mode = crs["mode"]
    if mode == "none":
        text = "no operator-level CRS requirement"
    elif mode == "declared":
        text = "must declare `starshine:crs`"
    elif mode == "projected":
        text = "must declare a projected `starshine:crs`"
    elif mode == "parameter":
        text = (
            f"coordinates are interpreted using parameter {inline_code(crs['parameter'], quote_strings=False)}"
            f" = {inline_code(crs.get('value'))}"
        )
    else:
        text = (
            "must either omit `starshine:crs` or match parameter "
            f"{inline_code(crs['parameter'], quote_strings=False)} = {inline_code(crs.get('value'))}"
        )
    if "equivalent_to_layer" in crs:
        text += f"; CRS must equal layer {inline_code(crs['equivalent_to_layer'], quote_strings=False)}"
    return text


def render_workflow_contract_markdown(contract: WorkflowContract) -> str:
    """Render a deterministic Markdown checklist for preparing external workflow layers."""
    layers = _validate_contract_for_render(contract)
    lines = [
        "# Starshine Workflow Input Contract",
        "",
        f"- Workflow version: {inline_code(contract['workflow_version'])}",
        f"- Declared external layers: {contract['layer_count']}",
        f"- Required external layers: {len(contract.get('required_external_layers', []))}",
        f"- Unused external layers: {len(contract.get('unused_external_layers', []))}",
        "",
    ]

    for layer in layers:
        lines.extend([f"## Layer {inline_code(layer['name'], quote_strings=False)}", ""])
        if layer["unused"]:
            lines.extend(["This declared layer is not referenced by the workflow.", ""])
            continue
        lines.append(f"Used by {layer['use_count']} workflow input(s).")
        lines.append("")
        for use in layer["uses"]:
            lines.extend(
                [
                    f"### Step {use['step_index']}: {inline_code(use['operation'], quote_strings=False)} / "
                    f"{inline_code(use['input_name'], quote_strings=False)}",
                    "",
                ]
            )
            geometry_text = (
                ", ".join(inline_code(value, quote_strings=False) for value in use["geometry_types"])
                if use["geometry_types"]
                else "any validated GeoJSON geometry type"
            )
            lines.extend(
                [
                    f"- Geometry: {geometry_text}",
                    f"- CRS: {_crs_text(use['crs'])}",
                ]
            )
            if use["required_fields"]:
                lines.append("- Required fields:")
                for field in use["required_fields"]:
                    constraints = []
                    if field["unique"]:
                        constraints.append("unique")
                    if field["non_null"]:
                        constraints.append("non-null")
                    if field["finite_json_scalar"]:
                        constraints.append("finite JSON scalar")
                    suffix = f" ({', '.join(constraints)})" if constraints else ""
                    lines.append(
                        f"  - {inline_code(field['name'], quote_strings=False)}{suffix}"
                    )
            else:
                lines.append("- Required fields: none")

            if use["written_fields"]:
                lines.append("- Fields written by the operator:")
                for field in use["written_fields"]:
                    lines.append(
                        f"  - {inline_code(field['name'], quote_strings=False)} "
                        f"(collision policy: {field['collision_policy']})"
                    )
            else:
                lines.append("- Fields written by the operator: none")
            for note in use["notes"]:
                lines.append(f"- Note: {note}")
            lines.append("")

    lines.extend(["## Remaining execution-time checks", ""])
    for message in contract.get("remaining_checks", []):
        lines.append(f"- {message}")
    lines.extend(
        [
            "",
            "## Evidence",
            "",
            f"- Workflow digest: {inline_code(contract['workflow_digest'], quote_strings=False)}",
            f"- Plan digest: {inline_code(contract['plan_digest'], quote_strings=False)}",
            f"- Contract digest: {inline_code(contract['contract_digest'], quote_strings=False)}",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "WORKFLOW_CONTRACT_VERSION",
    "WorkflowContract",
    "build_workflow_contract",
    "render_workflow_contract_markdown",
]
