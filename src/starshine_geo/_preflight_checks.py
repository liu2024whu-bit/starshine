from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any

from pyproj import CRS
from shapely.geometry import shape

from ._preflight_findings import _FindingCollector
from .crs import parse_crs
from .errors import ValidationError
from .geojson import FeatureCollection, validate_feature_collection
from .manifest import digest_json


def declared_crs_value(collection: FeatureCollection) -> str | None:
    value = collection.get("starshine:crs")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _parse_declared_crs(
    collection: FeatureCollection,
    *,
    layer_name: str,
    findings: _FindingCollector,
) -> tuple[str | None, CRS | None]:
    value = declared_crs_value(collection)
    if value is None:
        return None, None
    try:
        return value, parse_crs(value)
    except ValidationError:
        findings.add(
            severity="error",
            code="invalid_declared_crs",
            message="The declared starshine:crs value is not parseable.",
            layer=layer_name,
        )
        return value, None


def _parse_contract_crs(value: Any) -> CRS | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return parse_crs(value)
    except ValidationError:
        return None


def _effective_crs_for_use(
    *,
    layer_name: str,
    use: dict[str, Any],
    declared_value: str | None,
    declared_crs: CRS | None,
    findings: _FindingCollector,
) -> CRS | None:
    crs_contract = use["crs"]
    mode = crs_contract["mode"]
    context = {
        "layer": layer_name,
        "step_index": use["step_index"],
        "operation": use["operation"],
        "input_name": use["input_name"],
    }

    if mode in {"declared", "projected"} and declared_value is None:
        findings.add(
            severity="error",
            code="missing_declared_crs",
            message="This workflow input must declare starshine:crs.",
            **context,
        )
        return None

    if mode == "projected" and declared_crs is not None and not declared_crs.is_projected:
        findings.add(
            severity="error",
            code="non_projected_crs",
            message="This workflow input requires a projected CRS with linear units.",
            **context,
        )

    if mode == "parameter":
        parameter_crs = _parse_contract_crs(crs_contract.get("value"))
        if declared_crs is not None and parameter_crs is not None and not declared_crs.equals(
            parameter_crs
        ):
            findings.add(
                severity="error",
                code="declared_crs_conflicts_parameter",
                message="The declared CRS conflicts with the operator CRS parameter.",
                **context,
            )
        return parameter_crs

    if mode == "declared_or_parameter":
        parameter_crs = _parse_contract_crs(crs_contract.get("value"))
        if declared_crs is not None and parameter_crs is not None and not declared_crs.equals(
            parameter_crs
        ):
            findings.add(
                severity="error",
                code="declared_crs_conflicts_parameter",
                message="The declared CRS conflicts with the supplied source CRS parameter.",
                **context,
            )
        return parameter_crs

    return declared_crs


def _is_finite_json_scalar(value: Any) -> bool:
    if value is None or isinstance(value, (dict, list)):
        return False
    if not isinstance(value, (str, int, float, bool)):
        return False
    return not (isinstance(value, float) and not math.isfinite(value))


def _unique_key(value: Any) -> tuple[str, str] | None:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        return None
    return type(value).__name__, payload


def _check_required_field(
    *,
    layer_name: str,
    use: dict[str, Any],
    field_contract: dict[str, Any],
    features: list[dict[str, Any]],
    findings: _FindingCollector,
) -> None:
    field_name = field_contract["name"]
    context = {
        "layer": layer_name,
        "step_index": use["step_index"],
        "operation": use["operation"],
        "input_name": use["input_name"],
        "field_name": field_name,
    }
    seen: dict[tuple[str, str], int] = {}

    for index, feature in enumerate(features):
        properties = feature.get("properties") or {}
        if field_name not in properties:
            findings.add(
                severity="error",
                code="missing_required_field",
                message="A required property field is missing.",
                feature_index=index,
                **context,
            )
            continue

        value = properties[field_name]
        if field_contract["non_null"] and value is None:
            findings.add(
                severity="error",
                code="null_required_field",
                message="A required property field must not be null.",
                feature_index=index,
                **context,
            )
        if field_contract["finite_json_scalar"] and not _is_finite_json_scalar(value):
            findings.add(
                severity="error",
                code="non_scalar_required_field",
                message="A required property field must be a finite JSON scalar.",
                feature_index=index,
                **context,
            )

        skip_uniqueness = (field_contract["non_null"] and value is None) or (
            field_contract["finite_json_scalar"] and not _is_finite_json_scalar(value)
        )
        if field_contract["unique"] and not skip_uniqueness:
            key = _unique_key(value)
            if key is None:
                findings.add(
                    severity="error",
                    code="non_json_unique_field",
                    message="A unique property field contains a non-JSON value.",
                    feature_index=index,
                    **context,
                )
                continue
            if key in seen:
                findings.add(
                    severity="error",
                    code="duplicate_required_field",
                    message="A required property field contains duplicate values.",
                    feature_index=index,
                    **context,
                )
            else:
                seen[key] = index


def _check_written_fields(
    *,
    layer_name: str,
    use: dict[str, Any],
    features: list[dict[str, Any]],
    findings: _FindingCollector,
) -> None:
    written_fields = use["written_fields"]
    names: set[str] = set()
    for field_contract in written_fields:
        field_name = field_contract["name"]
        context = {
            "layer": layer_name,
            "step_index": use["step_index"],
            "operation": use["operation"],
            "input_name": use["input_name"],
            "field_name": field_name,
        }
        if field_name in names:
            findings.add(
                severity="error",
                code="duplicate_output_field",
                message="Two operator outputs resolve to the same property field.",
                **context,
            )
        names.add(field_name)

        if field_contract["collision_policy"] != "reject":
            continue
        for index, feature in enumerate(features):
            properties = feature.get("properties") or {}
            if field_name in properties:
                findings.add(
                    severity="error",
                    code="output_field_collision",
                    message="An output property field already exists on the input feature.",
                    feature_index=index,
                    **context,
                )


def summarize_layer(
    *,
    name: str,
    required: bool,
    unused: bool,
    collection: FeatureCollection,
    findings: _FindingCollector,
) -> tuple[dict[str, Any], FeatureCollection | None, CRS | None]:
    if unused:
        return (
            {
                "name": name,
                "required": required,
                "unused": True,
                "status": "skipped",
                "collection_digest": None,
                "feature_count": None,
                "declared_crs": declared_crs_value(collection),
                "geometry_counts": {},
                "error_count": 0,
                "warning_count": 0,
            },
            None,
            None,
        )

    try:
        validated = validate_feature_collection(collection)
    except ValidationError as exc:
        findings.add(
            severity="error",
            code="invalid_feature_collection",
            message=str(exc),
            layer=name,
        )
        return (
            {
                "name": name,
                "required": required,
                "unused": False,
                "status": "failed",
                "collection_digest": None,
                "feature_count": None,
                "declared_crs": declared_crs_value(collection),
                "geometry_counts": {},
                "error_count": 0,
                "warning_count": 0,
            },
            None,
            None,
        )

    geometry_counts: Counter[str] = Counter()
    for feature in validated["features"]:
        geometry_counts[shape(feature["geometry"]).geom_type] += 1

    try:
        collection_digest = digest_json(validated)
    except (TypeError, ValueError):
        collection_digest = None
        findings.add(
            severity="error",
            code="non_json_feature_collection",
            message="The FeatureCollection is not fully JSON serializable.",
            layer=name,
        )

    declared_value, declared_crs = _parse_declared_crs(
        validated,
        layer_name=name,
        findings=findings,
    )
    return (
        {
            "name": name,
            "required": required,
            "unused": False,
            "status": "pending",
            "collection_digest": collection_digest,
            "feature_count": len(validated["features"]),
            "declared_crs": declared_value,
            "geometry_counts": dict(sorted(geometry_counts.items())),
            "error_count": 0,
            "warning_count": 0,
        },
        validated,
        declared_crs,
    )


def check_layer_use(
    *,
    layer_name: str,
    use: dict[str, Any],
    collection: FeatureCollection,
    declared_crs: CRS | None,
    findings: _FindingCollector,
) -> CRS | None:
    """Check one external-layer use and return its effective CRS."""
    effective_crs = _effective_crs_for_use(
        layer_name=layer_name,
        use=use,
        declared_value=declared_crs_value(collection),
        declared_crs=declared_crs,
        findings=findings,
    )
    features = collection["features"]

    allowed_geometry_types = set(use["geometry_types"])
    if allowed_geometry_types:
        for index, feature in enumerate(features):
            geometry_type = shape(feature["geometry"]).geom_type
            if geometry_type not in allowed_geometry_types:
                findings.add(
                    severity="error",
                    code="unsupported_geometry_type",
                    message="A feature geometry type is not allowed for this workflow input.",
                    layer=layer_name,
                    step_index=use["step_index"],
                    operation=use["operation"],
                    input_name=use["input_name"],
                    feature_index=index,
                )

    for field_contract in use["required_fields"]:
        _check_required_field(
            layer_name=layer_name,
            use=use,
            field_contract=field_contract,
            features=features,
            findings=findings,
        )
    _check_written_fields(
        layer_name=layer_name,
        use=use,
        features=features,
        findings=findings,
    )
    return effective_crs

__all__ = ["check_layer_use", "declared_crs_value", "summarize_layer"]
