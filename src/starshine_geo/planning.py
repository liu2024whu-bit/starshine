from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from .manifest import digest_json
from .operator_registry import (
    OPERATOR_CATALOG_VERSION,
    OPERATOR_REGISTRY,
    operator_catalog,
)
from .workflow import validate_workflow

WORKFLOW_PLAN_VERSION = 1
WorkflowPlan = dict[str, Any]


def plan_workflow(workflow: dict[str, Any], layer_names: Iterable[str]) -> WorkflowPlan:
    """Validate and describe a workflow without reading feature data or running operators.

    The deterministic report resolves registry defaults, records step dependencies and layer
    provenance, and exposes each operator's declared output-CRS behavior. It cannot validate
    data-dependent rules such as actual geometry types or CRS equality between loaded layers.
    """
    declared_external_layers = sorted(set(layer_names))
    validate_workflow(workflow, declared_external_layers)

    producer_by_layer: dict[str, int] = {}
    consumed_layers: set[str] = set()
    required_external_layers: set[str] = set()
    produced_layers: list[str] = []
    planned_steps: list[dict[str, Any]] = []

    for index, step in enumerate(workflow["steps"]):
        operation = step["operation"]
        spec = OPERATOR_REGISTRY[operation]
        supplied_parameters = deepcopy(step.get("parameters", {}))
        parameters, parameter_sources = spec.public_parameters(supplied_parameters)

        inputs: dict[str, str] = {}
        input_sources: dict[str, dict[str, Any]] = {}
        dependencies: set[int] = set()

        for input_spec in spec.inputs:
            layer_name = step["inputs"][input_spec.name]
            inputs[input_spec.name] = layer_name
            consumed_layers.add(layer_name)

            if layer_name in producer_by_layer:
                producing_step = producer_by_layer[layer_name]
                dependencies.add(producing_step)
                input_sources[input_spec.name] = {
                    "kind": "step",
                    "layer": layer_name,
                    "step_index": producing_step,
                }
            else:
                required_external_layers.add(layer_name)
                input_sources[input_spec.name] = {
                    "kind": "external",
                    "layer": layer_name,
                }

        output_name = step["output"]
        producer_by_layer[output_name] = index
        produced_layers.append(output_name)
        planned_steps.append(
            {
                "index": index,
                "operation": operation,
                "summary": spec.summary,
                "inputs": inputs,
                "input_sources": input_sources,
                "parameters": parameters,
                "parameter_sources": parameter_sources,
                "output": output_name,
                "output_crs": spec.output_crs,
                "depends_on": sorted(dependencies),
                "deterministic": spec.deterministic,
            }
        )

    required_external = sorted(required_external_layers)
    terminal_layers = [name for name in produced_layers if name not in consumed_layers]
    plan: WorkflowPlan = {
        "schema_version": WORKFLOW_PLAN_VERSION,
        "workflow_version": workflow["version"],
        "workflow_digest": digest_json(workflow),
        "operator_catalog_version": OPERATOR_CATALOG_VERSION,
        "operator_catalog_digest": digest_json(operator_catalog()),
        "declared_external_layers": declared_external_layers,
        "required_external_layers": required_external,
        "unused_external_layers": sorted(set(declared_external_layers) - required_external_layers),
        "produced_layers": produced_layers,
        "terminal_layers": terminal_layers,
        "step_count": len(planned_steps),
        "steps": planned_steps,
    }
    plan["plan_digest"] = digest_json(plan)
    return plan


__all__ = ["WORKFLOW_PLAN_VERSION", "WorkflowPlan", "plan_workflow"]
