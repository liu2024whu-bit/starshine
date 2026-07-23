from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

_CRS_MODES = {
    "none",
    "declared",
    "projected",
    "parameter",
    "declared_or_parameter",
}
_COLLISION_POLICIES = {"reject", "overwrite"}


@dataclass(frozen=True, slots=True)
class FieldRequirementSpec:
    """One property field whose name is supplied by an operator parameter."""

    parameter: str
    unique: bool = False
    non_null: bool = False
    finite_json_scalar: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "unique": self.unique,
            "non_null": self.non_null,
            "finite_json_scalar": self.finite_json_scalar,
        }

    def resolve(self, parameters: Mapping[str, Any]) -> dict[str, Any] | None:
        value = parameters.get(self.parameter)
        if value is None:
            return None
        return {
            "name": deepcopy(value),
            "source_parameter": self.parameter,
            "unique": self.unique,
            "non_null": self.non_null,
            "finite_json_scalar": self.finite_json_scalar,
        }


@dataclass(frozen=True, slots=True)
class FieldWriteSpec:
    """One property field written by an operator and its collision policy."""

    collision_policy: str
    parameter: str | None = None
    name: str | None = None

    def __post_init__(self) -> None:
        if self.collision_policy not in _COLLISION_POLICIES:
            raise ValueError(f"unsupported collision policy: {self.collision_policy}")
        if (self.parameter is None) == (self.name is None):
            raise ValueError("field writes require exactly one of parameter or name")

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"collision_policy": self.collision_policy}
        if self.parameter is not None:
            result["parameter"] = self.parameter
        else:
            result["name"] = self.name
        return result

    def resolve(self, parameters: Mapping[str, Any]) -> dict[str, Any] | None:
        if self.parameter is not None:
            value = parameters.get(self.parameter)
            if value is None:
                return None
            return {
                "name": deepcopy(value),
                "source_parameter": self.parameter,
                "collision_policy": self.collision_policy,
            }
        return {
            "name": self.name,
            "collision_policy": self.collision_policy,
        }


@dataclass(frozen=True, slots=True)
class InputContractSpec:
    """Declarative, data-free requirements for one named operator input."""

    geometry_types: tuple[str, ...] = ()
    crs_mode: str = "none"
    crs_parameter: str | None = None
    equivalent_crs_to: str | None = None
    required_fields: tuple[FieldRequirementSpec, ...] = ()
    written_fields: tuple[FieldWriteSpec, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.crs_mode not in _CRS_MODES:
            raise ValueError(f"unsupported CRS contract mode: {self.crs_mode}")
        if self.crs_mode in {"parameter", "declared_or_parameter"}:
            if self.crs_parameter is None:
                raise ValueError(f"{self.crs_mode} CRS contracts require crs_parameter")
        elif self.crs_parameter is not None:
            raise ValueError(f"{self.crs_mode} CRS contracts cannot define crs_parameter")

    def as_dict(self) -> dict[str, Any]:
        crs: dict[str, Any] = {"mode": self.crs_mode}
        if self.crs_parameter is not None:
            crs["parameter"] = self.crs_parameter
        if self.equivalent_crs_to is not None:
            crs["equivalent_to_input"] = self.equivalent_crs_to
        return {
            "geometry_types": list(self.geometry_types),
            "crs": crs,
            "required_fields": [item.as_dict() for item in self.required_fields],
            "written_fields": [item.as_dict() for item in self.written_fields],
            "notes": list(self.notes),
        }


__all__ = [
    "FieldRequirementSpec",
    "FieldWriteSpec",
    "InputContractSpec",
]
