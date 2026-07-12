from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from .errors import UnsupportedOperationError, ValidationError
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


def run_workflow(workflow: dict[str, Any], layers: Context) -> Context:
    """Execute a bounded workflow using an explicit operator registry—never dynamic eval."""
    if workflow.get("version") != 1:
        raise ValidationError("workflow.version must equal 1")
    steps = workflow.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValidationError("workflow.steps must be a non-empty list")

    context = {name: validate_feature_collection(value) for name, value in layers.items()}
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValidationError(f"step {index} must be an object")
        operation = step.get("operation")
        output_name = step.get("output")
        if operation not in OPERATORS:
            raise UnsupportedOperationError(f"unsupported operation: {operation!r}")
        if not isinstance(output_name, str) or not output_name.strip():
            raise ValidationError(f"step {index}.output must be a non-empty string")
        if output_name in context:
            raise ValidationError(f"step {index} would overwrite layer: {output_name}")
        context[output_name] = OPERATORS[operation](context, step)
    return context
