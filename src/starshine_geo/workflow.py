from __future__ import annotations

import math
from copy import deepcopy
from typing import Any, Callable, Iterable

from .crs import parse_crs, require_projected_crs
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
ParameterValidator = Callable[[Any], str | None]

_STEP_FIELDS = {"operation", "inputs", "parameters", "output"}
_ROOT_FIELDS = {"version", "steps"}


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


def _validate_positive_number(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "must be a number"
    if not math.isfinite(float(value)) or float(value) <= 0:
        return "must be a positive finite number"
    return None


def _validate_non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return "must be a non-empty string"
    return None


def _validate_segments(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return "must be an integer between 1 and 64"
    if not 1 <= value <= 64:
        return "must be an integer between 1 and 64"
    return None


def _validate_optional_field_name(value: Any) -> str | None:
    if value is None:
        return None
    return _validate_non_empty_string(value)


def _validate_source_crs(value: Any) -> str | None:
    message = _validate_non_empty_string(value)
    if message is not None:
        return message
    try:
        parse_crs(value)
    except ValidationError as exc:
        return str(exc)
    return None


def _validate_work_crs(value: Any) -> str | None:
    message = _validate_non_empty_string(value)
    if message is not None:
        return message
    try:
        require_projected_crs(value)
    except ValidationError as exc:
        return str(exc)
    return None


OPERATOR_PARAMETER_SPECS: dict[str, dict[str, dict[str, ParameterValidator]]] = {
    "buffer": {
        "required": {
            "distance": _validate_positive_number,
            "source_crs": _validate_source_crs,
            "work_crs": _validate_work_crs,
        },
        "optional": {
            "segments": _validate_segments,
        },
    },
    "dissolve": {
        "required": {},
        "optional": {
            "group_field": _validate_optional_field_name,
        },
    },
    "summarize_points_within": {
        "required": {},
        "optional": {
            "polygon_id_field": _validate_non_empty_string,
            "count_field": _validate_non_empty_string,
        },
    },
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


def _raise_diagnostic(
    *,
    code: str,
    message: str,
    path: str,
    step_index: int | None = None,
    operation: str | None = None,
) -> None:
    raise WorkflowValidationError(
        _diagnostic(
            code=code,
            message=message,
            path=path,
            step_index=step_index,
            operation=operation,
        )
    )


def _validate_parameters(
    parameters: dict[str, Any],
    *,
    operation: str,
    step_index: int,
    step_path: str,
) -> None:
    spec = OPERATOR_PARAMETER_SPECS[operation]
    required = spec["required"]
    optional = spec["optional"]
    allowed = set(required) | set(optional)

    unexpected = sorted(set(parameters) - allowed)
    if unexpected:
        name = unexpected[0]
        _raise_diagnostic(
            code="unexpected_parameter",
            message=f"unexpected parameter for {operation}: {name}",
            path=f"{step_path}.parameters.{name}",
            step_index=step_index,
            operation=operation,
        )

    for name, validator in required.items():
        if name not in parameters:
            _raise_diagnostic(
                code="missing_parameter",
                message=f"missing required parameter for {operation}: {name}",
                path=f"{step_path}.parameters.{name}",
                step_index=step_index,
                operation=operation,
            )
        error = validator(parameters[name])
        if error is not None:
            _raise_diagnostic(
                code="invalid_parameter",
                message=f"{operation}.{name} {error}",
                path=f"{step_path}.parameters.{name}",
                step_index=step_index,
                operation=operation,
            )

    for name, validator in optional.items():
        if name not in parameters:
            continue
        error = validator(parameters[name])
        if error is not None:
            _raise_diagnostic(
                code="invalid_parameter",
                message=f"{operation}.{name} {error}",
                path=f"{step_path}.parameters.{name}",
                step_index=step_index,
                operation=operation,
            )


def validate_workflow(workflow: Any, layer_names: Iterable[str]) -> None:
    """Validate the complete workflow structure and parameters before execution."""
    if not isinstance(workflow, dict):
        _raise_diagnostic(
            code="invalid_workflow",
            message="workflow must be an object",
            path="$",
        )

    unexpected_root = sorted(set(workflow) - _ROOT_FIELDS)
    if unexpected_root:
        name = unexpected_root[0]
        _raise_diagnostic(
            code="unexpected_workflow_field",
            message=f"unexpected workflow field: {name}",
            path=name,
        )

    if workflow.get("version") != 1:
        _raise_diagnostic(
            code="unsupported_version",
            message="workflow.version must equal 1",
            path="version",
        )

    steps = workflow.get("steps")
    if not isinstance(steps, list) or not steps:
        _raise_diagnostic(
            code="invalid_steps",
            message="workflow.steps must be a non-empty list",
            path="steps",
        )

    available_layers = set(layer_names)
    for index, step in enumerate(steps):
        step_path = f"steps[{index}]"
        if not isinstance(step, dict):
            _raise_diagnostic(
                code="invalid_step",
                message=f"step {index} must be an object",
                path=step_path,
                step_index=index,
            )

        unexpected_step_fields = sorted(set(step) - _STEP_FIELDS)
        if unexpected_step_fields:
            name = unexpected_step_fields[0]
            _raise_diagnostic(
                code="unexpected_step_field",
                message=f"unexpected step field: {name}",
                path=f"{step_path}.{name}",
                step_index=index,
            )

        operation = step.get("operation")
        if not isinstance(operation, str) or not operation.strip():
            _raise_diagnostic(
                code="invalid_operation",
                message=f"step {index}.operation must be a non-empty string",
                path=f"{step_path}.operation",
                step_index=index,
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
            _raise_diagnostic(
                code="invalid_inputs",
                message=f"step {index}.inputs must be an object",
                path=f"{step_path}.inputs",
                step_index=index,
                operation=operation,
            )

        allowed_inputs = set(OPERATOR_INPUTS[operation])
        unexpected_inputs = sorted(set(inputs) - allowed_inputs)
        if unexpected_inputs:
            name = unexpected_inputs[0]
            _raise_diagnostic(
                code="unexpected_input",
                message=f"unexpected input for {operation}: {name}",
                path=f"{step_path}.inputs.{name}",
                step_index=index,
                operation=operation,
            )

        for input_name in OPERATOR_INPUTS[operation]:
            input_path = f"{step_path}.inputs.{input_name}"
            layer_name = inputs.get(input_name)
            if not isinstance(layer_name, str) or not layer_name.strip():
                _raise_diagnostic(
                    code="invalid_input_reference",
                    message=f"step {index}.inputs.{input_name} must name a context layer",
                    path=input_path,
                    step_index=index,
                    operation=operation,
                )
            if layer_name not in available_layers:
                _raise_diagnostic(
                    code="unknown_input_layer",
                    message=f"unknown input layer: {layer_name}",
                    path=input_path,
                    step_index=index,
                    operation=operation,
                )

        parameters = step.get("parameters", {})
        if not isinstance(parameters, dict):
            _raise_diagnostic(
                code="invalid_parameters",
                message=f"step {index}.parameters must be an object",
                path=f"{step_path}.parameters",
                step_index=index,
                operation=operation,
            )
        _validate_parameters(
            parameters,
            operation=operation,
            step_index=index,
            step_path=step_path,
        )

        output_name = step.get("output")
        if not isinstance(output_name, str) or not output_name.strip():
            _raise_diagnostic(
                code="invalid_output",
                message=f"step {index}.output must be a non-empty string",
                path=f"{step_path}.output",
                step_index=index,
                operation=operation,
            )
        if output_name in available_layers:
            _raise_diagnostic(
                code="output_overwrite",
                message=f"step {index} would overwrite layer: {output_name}",
                path=f"{step_path}.output",
                step_index=index,
                operation=operation,
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
