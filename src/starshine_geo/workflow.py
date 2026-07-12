from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Iterable

from .errors import (
    UnsupportedOperationError,
    ValidationError,
    WorkflowDiagnostic,
    WorkflowValidationError,
)
from .geojson import FeatureCollection, validate_feature_collection
from .operators import buffer_features, dissolve_features, summarize_points_within

Context = dict[str, FeatureCollection]
Operator = Callable[..., FeatureCollection]


def _buffer(context: Context, step: dict[str, Any]) -> FeatureCollection:
    source = _layer(context, step, "input")
    return buffer_features(source, **_parameters(step))


def _dissolve(context: Context, step: dict[str, Any]) -> FeatureCollection:
    source = _layer(context, step, "input")
    return dissolve_features(source, **_parameters(step))


def _summarize(context: Context, step: dict[str, Any]) -> FeatureCollection:
    polygons = _layer(context, step, "polygons")
    points = _layer(context, step, "points")
    return summarize_points_within(polygons, points, **_parameters(step))


OPERATORS: dict[str, Operator] = {
    "buffer": _buffer,
    "dissolve": _dissolve,
    "summarize_points_within": _summarize,
}

OPERATOR_INPUTS: dict[str, tuple[str, ...]] = {
    "buffer": ("input",),
    "dissolve": ("input",),
    "summarize_points_within": ("polygons", "points"),
}


def _parameters(step: dict[str, Any]) -> dict[str, Any]:
    value = step.get("parameters", {})
    if not isinstance(value, dict):
        raise ValidationError("step.parameters must be an object")
    return deepcopy(value)


def _layer(context: Context, step: dict[str, Any], name: str) -> FeatureCollection:
    inputs = step.get("inputs")
    if not isinstance(inputs, dict) or not isinstance(inputs.get(name), str):
        raise ValidationError(f"step.inputs.{name} must name a context layer")
    layer_name = inputs[name]
    if layer_name not in context:
        raise ValidationError(f"unknown input layer: {layer_name}")
    return context[layer_name]


def _diagnostic(
    *,
    code: str,
    message: str,
    path: str,
    step_index: int | None = None,
    operation: str | None = None,
) -> WorkflowDiagnostic:
    return WorkflowDiagnostic(
        code=code,
        message=message,
        path=path,
        step_index=step_index,
        operation=operation,
    )


def validate_workflow(workflow: Any, layer_names: Iterable[str]) -> None:
    """Validate the complete workflow structure before any operator executes."""
    if not isinstance(workflow, dict):
        raise WorkflowValidationError(
            _diagnostic(
                code="invalid_workflow",
                message="workflow must be an object",
                path="$",
            )
        )
    if workflow.get("version") != 1:
        raise WorkflowValidationError(
            _diagnostic(
                code="unsupported_version",
                message="workflow.version must equal 1",
                path="version",
            )
        )

    steps = workflow.get("steps")
    if not isinstance(steps, list) or not steps:
        raise WorkflowValidationError(
            _diagnostic(
                code="invalid_steps",
                message="workflow.steps must be a non-empty list",
                path="steps",
            )
        )

    available_layers = set(layer_names)
    for index, step in enumerate(steps):
        step_path = f"steps[{index}]"
        if not isinstance(step, dict):
            raise WorkflowValidationError(
                _diagnostic(
                    code="invalid_step",
                    message=f"step {index} must be an object",
                    path=step_path,
                    step_index=index,
                )
            )

        operation = step.get("operation")
        if not isinstance(operation, str) or not operation.strip():
            raise WorkflowValidationError(
                _diagnostic(
                    code="invalid_operation",
                    message=f"step {index}.operation must be a non-empty string",
                    path=f"{step_path}.operation",
                    step_index=index,
                )
            )
        if operation not in OPERATORS:
            raise UnsupportedOperationError(
                _diagnostic(
                    code="unsupported_operation",
                    message=f"unsupported operation: {operation!r}",
                    path=f"{step_path}.operation",
                    step_index=index,
                    operation=operation,
                )
            )

        inputs = step.get("inputs")
        if not isinstance(inputs, dict):
            raise WorkflowValidationError(
                _diagnostic(
                    code="invalid_inputs",
                    message=f"step {index}.inputs must be an object",
                    path=f"{step_path}.inputs",
                    step_index=index,
                    operation=operation,
                )
            )
        for input_name in OPERATOR_INPUTS[operation]:
            input_path = f"{step_path}.inputs.{input_name}"
            layer_name = inputs.get(input_name)
            if not isinstance(layer_name, str) or not layer_name.strip():
                raise WorkflowValidationError(
                    _diagnostic(
                        code="invalid_input_reference",
                        message=(
                            f"step {index}.inputs.{input_name} must name a context layer"
                        ),
                        path=input_path,
                        step_index=index,
                        operation=operation,
                    )
                )
            if layer_name not in available_layers:
                raise WorkflowValidationError(
                    _diagnostic(
                        code="unknown_input_layer",
                        message=f"unknown input layer: {layer_name}",
                        path=input_path,
                        step_index=index,
                        operation=operation,
                    )
                )

        parameters = step.get("parameters", {})
        if not isinstance(parameters, dict):
            raise WorkflowValidationError(
                _diagnostic(
                    code="invalid_parameters",
                    message=f"step {index}.parameters must be an object",
                    path=f"{step_path}.parameters",
                    step_index=index,
                    operation=operation,
                )
            )

        output_name = step.get("output")
        if not isinstance(output_name, str) or not output_name.strip():
            raise WorkflowValidationError(
                _diagnostic(
                    code="invalid_output",
                    message=f"step {index}.output must be a non-empty string",
                    path=f"{step_path}.output",
                    step_index=index,
                    operation=operation,
                )
            )
        if output_name in available_layers:
            raise WorkflowValidationError(
                _diagnostic(
                    code="output_overwrite",
                    message=f"step {index} would overwrite layer: {output_name}",
                    path=f"{step_path}.output",
                    step_index=index,
                    operation=operation,
                )
            )
        available_layers.add(output_name)


def run_workflow(workflow: dict[str, Any], layers: Context) -> Context:
    """Execute a bounded workflow using an explicit operator registry—never dynamic eval."""
    validate_workflow(workflow, layers)
    steps = workflow["steps"]

    context = {name: validate_feature_collection(value) for name, value in layers.items()}
    for step in steps:
        operation = step["operation"]
        output_name = step["output"]
        context[output_name] = OPERATORS[operation](context, step)
    return context
