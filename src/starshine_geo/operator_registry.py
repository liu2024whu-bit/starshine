from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .crs import parse_crs, require_projected_crs
from .errors import ValidationError
from .geojson import FeatureCollection
from .operators import (
    buffer_features,
    dissolve_features,
    reproject_features,
    summarize_points_within,
)

ParameterValidator = Callable[[Any], str | None]
OperatorExecutor = Callable[[dict[str, FeatureCollection], dict[str, Any]], FeatureCollection]

_MISSING = object()
OPERATOR_CATALOG_VERSION = 1
WORKFLOW_VERSION = 1


@dataclass(frozen=True, slots=True)
class InputSpec:
    """One named input expected by a workflow operator."""

    name: str
    description: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description}


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    """Runtime validation and public documentation for one operator parameter."""

    name: str
    description: str
    schema: dict[str, Any]
    validator: ParameterValidator
    required: bool = False
    default: Any = _MISSING

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "required": self.required,
            "schema": deepcopy(self.schema),
        }
        if self.default is not _MISSING:
            result["default"] = deepcopy(self.default)
        return result


@dataclass(frozen=True, slots=True)
class OperatorSpec:
    """Executable and machine-readable definition of one bounded operator."""

    name: str
    summary: str
    inputs: tuple[InputSpec, ...]
    parameters: tuple[ParameterSpec, ...]
    output_crs: str
    executor: OperatorExecutor
    deterministic: bool = True

    @property
    def input_names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.inputs)

    @property
    def required_parameters(self) -> dict[str, ParameterValidator]:
        return {item.name: item.validator for item in self.parameters if item.required}

    @property
    def optional_parameters(self) -> dict[str, ParameterValidator]:
        return {item.name: item.validator for item in self.parameters if not item.required}

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "inputs": [item.as_dict() for item in self.inputs],
            "parameters": [item.as_dict() for item in self.parameters],
            "output_crs": self.output_crs,
            "deterministic": self.deterministic,
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


def _validate_crs(value: Any) -> str | None:
    message = _validate_non_empty_string(value)
    if message is not None:
        return message
    try:
        parse_crs(value)
    except ValidationError as exc:
        return str(exc)
    return None


def _validate_optional_crs(value: Any) -> str | None:
    if value is None:
        return None
    return _validate_crs(value)


def _validate_work_crs(value: Any) -> str | None:
    message = _validate_non_empty_string(value)
    if message is not None:
        return message
    try:
        require_projected_crs(value)
    except ValidationError as exc:
        return str(exc)
    return None


def _execute_buffer(
    inputs: dict[str, FeatureCollection], parameters: dict[str, Any]
) -> FeatureCollection:
    return buffer_features(inputs["input"], **parameters)


def _execute_dissolve(
    inputs: dict[str, FeatureCollection], parameters: dict[str, Any]
) -> FeatureCollection:
    return dissolve_features(inputs["input"], **parameters)


def _execute_summary(
    inputs: dict[str, FeatureCollection], parameters: dict[str, Any]
) -> FeatureCollection:
    return summarize_points_within(inputs["polygons"], inputs["points"], **parameters)


def _execute_reproject(
    inputs: dict[str, FeatureCollection], parameters: dict[str, Any]
) -> FeatureCollection:
    return reproject_features(inputs["input"], **parameters)


_OPERATOR_SPECS = (
    OperatorSpec(
        name="buffer",
        summary="Buffer every input feature in an explicitly projected working CRS.",
        inputs=(InputSpec("input", "FeatureCollection to buffer."),),
        parameters=(
            ParameterSpec(
                "distance",
                "Positive buffer distance expressed in the working CRS linear unit.",
                {"type": "number", "exclusiveMinimum": 0},
                _validate_positive_number,
                required=True,
            ),
            ParameterSpec(
                "source_crs",
                "CRS describing the input coordinates.",
                {"type": "string", "minLength": 1, "pattern": "\\S"},
                _validate_crs,
                required=True,
            ),
            ParameterSpec(
                "work_crs",
                "Projected CRS used for the distance operation.",
                {"type": "string", "minLength": 1, "pattern": "\\S"},
                _validate_work_crs,
                required=True,
            ),
            ParameterSpec(
                "segments",
                "Quarter-circle segments used by the buffer approximation.",
                {"type": "integer", "minimum": 1, "maximum": 64},
                _validate_segments,
                default=16,
            ),
        ),
        output_crs="source_crs parameter",
        executor=_execute_buffer,
    ),
    OperatorSpec(
        name="dissolve",
        summary="Union all input geometries, optionally grouped by one property field.",
        inputs=(InputSpec("input", "FeatureCollection whose geometries will be dissolved."),),
        parameters=(
            ParameterSpec(
                "group_field",
                "Optional property field used to partition features before union.",
                {
                    "anyOf": [
                        {"type": "string", "minLength": 1, "pattern": "\\S"},
                        {"type": "null"},
                    ]
                },
                _validate_optional_field_name,
                default=None,
            ),
        ),
        output_crs="input layer",
        executor=_execute_dissolve,
    ),
    OperatorSpec(
        name="summarize_points_within",
        summary="Count Point features covered by each polygon feature.",
        inputs=(
            InputSpec("polygons", "Polygon FeatureCollection whose properties are preserved."),
            InputSpec("points", "Point FeatureCollection to count."),
        ),
        parameters=(
            ParameterSpec(
                "polygon_id_field",
                "Required unique polygon property used to detect duplicate identifiers.",
                {"type": "string", "minLength": 1, "pattern": "\\S"},
                _validate_non_empty_string,
                default="id",
            ),
            ParameterSpec(
                "count_field",
                "Output property that receives the point count.",
                {"type": "string", "minLength": 1, "pattern": "\\S"},
                _validate_non_empty_string,
                default="point_count",
            ),
        ),
        output_crs="polygons input layer",
        executor=_execute_summary,
    ),
    OperatorSpec(
        name="reproject",
        summary="Transform every geometry to a target CRS while preserving properties and order.",
        inputs=(InputSpec("input", "FeatureCollection to transform."),),
        parameters=(
            ParameterSpec(
                "target_crs",
                "CRS assigned to and used for the transformed output coordinates.",
                {"type": "string", "minLength": 1, "pattern": "\\S"},
                _validate_crs,
                required=True,
            ),
            ParameterSpec(
                "source_crs",
                "Optional source CRS; required only when the input has no starshine:crs value.",
                {
                    "anyOf": [
                        {"type": "string", "minLength": 1, "pattern": "\\S"},
                        {"type": "null"},
                    ]
                },
                _validate_optional_crs,
                default=None,
            ),
        ),
        output_crs="target_crs parameter",
        executor=_execute_reproject,
    ),
)

OPERATOR_REGISTRY: Mapping[str, OperatorSpec] = MappingProxyType(
    {spec.name: spec for spec in _OPERATOR_SPECS}
)


def operator_catalog() -> dict[str, Any]:
    """Return the stable, JSON-ready catalog for all registered public operators."""
    return {
        "schema_version": OPERATOR_CATALOG_VERSION,
        "workflow_version": WORKFLOW_VERSION,
        "operators": [spec.as_dict() for spec in _OPERATOR_SPECS],
    }


__all__ = [
    "InputSpec",
    "OPERATOR_CATALOG_VERSION",
    "OPERATOR_REGISTRY",
    "OperatorSpec",
    "ParameterSpec",
    "WORKFLOW_VERSION",
    "operator_catalog",
]
