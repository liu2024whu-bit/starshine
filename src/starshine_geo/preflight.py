from __future__ import annotations

import json
import math
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from pyproj import CRS
from shapely.geometry import shape

from ._markdown import inline_code
from .contracts import build_workflow_contract
from .crs import parse_crs
from .errors import ValidationError
from .geojson import FeatureCollection, validate_feature_collection
from .manifest import digest_json

WORKFLOW_PREFLIGHT_VERSION = 1
WorkflowPreflight = dict[str, Any]

_MAX_SAMPLE_INDEXES = 20

_REMAINING_CHECKS = (
    "CRS equivalence involving a layer produced by an earlier step remains deferred to execution.",
    "Produced-layer geometry and property contracts can only be checked after their producer runs.",
    "Spatial relationships, distances, ambiguity outcomes, and empty results require operator execution.",
    "Output feature counts and post-execution manifest digests require running the workflow.",
)


@dataclass(slots=True)
class _FindingBucket:
    severity: str
    code: str
    message: str
    layer: str
    step_index: int | None = None
    operation: str | None = None
    input_name: str | None = None
    field_name: str | None = None
    occurrence_count: int = 0
    feature_indexes: list[int] = field(default_factory=list)

    def add(self, feature_index: int | None = None) -> None:
        self.occurrence_count += 1
        if feature_index is not None and len(self.feature_indexes) < _MAX_SAMPLE_INDEXES:
            self.feature_indexes.append(feature_index)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "layer": self.layer,
            "occurrence_count": self.occurrence_count,
        }
        if self.step_index is not None:
            result["step_index"] = self.step_index
        if self.operation is not None:
            result["operation"] = self.operation
        if self.input_name is not None:
            result["input_name"] = self.input_name
        if self.field_name is not None:
            result["field"] = self.field_name
        if self.feature_indexes:
            result["feature_indexes"] = list(self.feature_indexes)
        return result


class _FindingCollector:
    def __init__(self) -> None:
        self._buckets: dict[tuple[Any, ...], _FindingBucket] = {}

    def add(
        self,
        *,
        severity: str,
        code: str,
        message: str,
        layer: str,
        step_index: int | None = None,
        operation: str | None = None,
        input_name: str | None = None,
        field_name: str | None = None,
        feature_index: int | None = None,
    ) -> None:
        key = (
            severity,
            code,
            message,
            layer,
            step_index,
            operation,
            input_name,
            field_name,
        )
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _FindingBucket(
                severity=severity,
                code=code,
                message=message,
                layer=layer,
                step_index=step_index,
                operation=operation,
                input_name=input_name,
                field_name=field_name,
            )
            self._buckets[key] = bucket
        bucket.add(feature_index)

    def findings(self) -> list[dict[str, Any]]:
        return [bucket.as_dict() for bucket in self._buckets.values()]


def _declared_crs_value(collection: FeatureCollection) -> str | None:
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
    value = _declared_crs_value(collection)
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


def _layer_summary(
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
                "declared_crs": _declared_crs_value(collection),
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
                "declared_crs": _declared_crs_value(collection),
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


def preflight_workflow_inputs(
    workflow: dict[str, Any],
    layers: Mapping[str, FeatureCollection],
) -> WorkflowPreflight:
    """Check loaded external layers against planner-derived workflow contracts.

    Structural validation, ordering, defaults, and input provenance come from the canonical planner
    through ``build_workflow_contract``. This function validates and inspects external collections
    but never executes a spatial operator or creates produced layers.
    """
    contract = build_workflow_contract(workflow, layers.keys())
    findings = _FindingCollector()
    summaries: list[dict[str, Any]] = []
    validated_layers: dict[str, FeatureCollection] = {}
    declared_crs_by_layer: dict[str, CRS | None] = {}
    layer_contracts = {layer["name"]: layer for layer in contract["layers"]}

    for layer_contract in contract["layers"]:
        name = layer_contract["name"]
        summary, validated, declared_crs = _layer_summary(
            name=name,
            required=layer_contract["required"],
            unused=layer_contract["unused"],
            collection=layers[name],
            findings=findings,
        )
        summaries.append(summary)
        if validated is not None:
            validated_layers[name] = validated
            declared_crs_by_layer[name] = declared_crs

    effective_crs_by_use: dict[tuple[int, str], CRS | None] = {}
    layer_by_use: dict[tuple[int, str], str] = {}

    for layer_contract in contract["layers"]:
        layer_name = layer_contract["name"]
        validated = validated_layers.get(layer_name)
        if validated is None:
            continue
        declared_value = _declared_crs_value(validated)
        declared_crs = declared_crs_by_layer[layer_name]
        features = validated["features"]

        for use in layer_contract["uses"]:
            use_key = (use["step_index"], use["input_name"])
            layer_by_use[use_key] = layer_name
            effective_crs_by_use[use_key] = _effective_crs_for_use(
                layer_name=layer_name,
                use=use,
                declared_value=declared_value,
                declared_crs=declared_crs,
                findings=findings,
            )

            allowed_geometry_types = set(use["geometry_types"])
            if allowed_geometry_types:
                for index, feature in enumerate(features):
                    geometry_type = shape(feature["geometry"]).geom_type
                    if geometry_type not in allowed_geometry_types:
                        findings.add(
                            severity="error",
                            code="unsupported_geometry_type",
                            message=(
                                "A feature geometry type is not allowed for this workflow input."
                            ),
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

    checked_equivalence: set[tuple[int, str, str]] = set()
    for layer_contract in contract["layers"]:
        layer_name = layer_contract["name"]
        for use in layer_contract["uses"]:
            other_layer = use["crs"].get("equivalent_to_layer")
            if other_layer is None:
                continue
            pair = (use["step_index"], *sorted((layer_name, other_layer)))
            if pair in checked_equivalence:
                continue
            checked_equivalence.add(pair)

            current_key = (use["step_index"], use["input_name"])
            other_keys = [
                key
                for key, candidate_layer in layer_by_use.items()
                if key[0] == use["step_index"] and candidate_layer == other_layer
            ]
            if not other_keys:
                findings.add(
                    severity="warning",
                    code="deferred_crs_equivalence",
                    message=(
                        "CRS equivalence depends on a layer produced by an earlier workflow step."
                    ),
                    layer=layer_name,
                    step_index=use["step_index"],
                    operation=use["operation"],
                    input_name=use["input_name"],
                )
                continue

            current_crs = effective_crs_by_use.get(current_key)
            other_crs = effective_crs_by_use.get(other_keys[0])
            if current_crs is not None and other_crs is not None and not current_crs.equals(other_crs):
                findings.add(
                    severity="error",
                    code="crs_mismatch",
                    message="Workflow inputs that must share a CRS are not equivalent.",
                    layer=layer_name,
                    step_index=use["step_index"],
                    operation=use["operation"],
                    input_name=use["input_name"],
                )

    finding_values = findings.findings()
    counts_by_layer: dict[str, Counter[str]] = {
        name: Counter() for name in layer_contracts
    }
    for finding in finding_values:
        counts_by_layer[finding["layer"]][finding["severity"]] += finding["occurrence_count"]

    for summary in summaries:
        counts = counts_by_layer[summary["name"]]
        summary["error_count"] = counts["error"]
        summary["warning_count"] = counts["warning"]
        if summary["status"] == "pending":
            summary["status"] = "failed" if counts["error"] else "passed"

    error_count = sum(
        finding["occurrence_count"]
        for finding in finding_values
        if finding["severity"] == "error"
    )
    warning_count = sum(
        finding["occurrence_count"]
        for finding in finding_values
        if finding["severity"] == "warning"
    )
    report: WorkflowPreflight = {
        "schema_version": WORKFLOW_PREFLIGHT_VERSION,
        "workflow_version": contract["workflow_version"],
        "workflow_digest": contract["workflow_digest"],
        "operator_catalog_version": contract["operator_catalog_version"],
        "operator_catalog_digest": contract["operator_catalog_digest"],
        "plan_digest": contract["plan_digest"],
        "contract_digest": contract["contract_digest"],
        "valid": error_count == 0,
        "layer_count": len(summaries),
        "checked_layer_count": sum(1 for item in summaries if item["status"] != "skipped"),
        "error_count": error_count,
        "warning_count": warning_count,
        "layers": summaries,
        "findings": finding_values,
        "remaining_checks": list(_REMAINING_CHECKS),
    }
    report["preflight_digest"] = digest_json(report)
    return report


def _validate_preflight_for_render(report: WorkflowPreflight) -> None:
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise ValidationError("workflow preflight report must use schema version 1")
    if not isinstance(report.get("layers"), list):
        raise ValidationError("workflow preflight report must contain a layers array")
    if not isinstance(report.get("findings"), list):
        raise ValidationError("workflow preflight report must contain a findings array")


def render_workflow_preflight_markdown(report: WorkflowPreflight) -> str:
    """Render a deterministic Markdown summary of actual workflow input checks."""
    _validate_preflight_for_render(report)
    status = "PASS" if report["valid"] else "FAIL"
    lines = [
        "# Starshine Workflow Input Preflight",
        "",
        f"- Status: **{status}**",
        f"- Checked layers: {report['checked_layer_count']} / {report['layer_count']}",
        f"- Errors: {report['error_count']}",
        f"- Warnings: {report['warning_count']}",
        "",
    ]

    findings_by_layer: dict[str, list[dict[str, Any]]] = {}
    for finding in report["findings"]:
        findings_by_layer.setdefault(finding["layer"], []).append(finding)

    for layer in report["layers"]:
        lines.extend(
            [
                f"## Layer {inline_code(layer['name'], quote_strings=False)}",
                "",
                f"- Status: {layer['status']}",
                f"- Required: {'yes' if layer['required'] else 'no'}",
                f"- Declared CRS: {inline_code(layer['declared_crs'])}",
            ]
        )
        if layer["feature_count"] is not None:
            lines.append(f"- Features: {layer['feature_count']}")
        if layer["geometry_counts"]:
            geometry_text = ", ".join(
                f"{inline_code(name, quote_strings=False)} × {count}"
                for name, count in layer["geometry_counts"].items()
            )
            lines.append(f"- Geometry: {geometry_text}")
        layer_findings = findings_by_layer.get(layer["name"], [])
        if layer_findings:
            lines.append("- Findings:")
            for finding in layer_findings:
                context = []
                if "step_index" in finding:
                    context.append(f"step {finding['step_index']}")
                if "input_name" in finding:
                    context.append(f"input {inline_code(finding['input_name'], quote_strings=False)}")
                if "field" in finding:
                    context.append(f"field {inline_code(finding['field'], quote_strings=False)}")
                suffix = f" ({', '.join(context)})" if context else ""
                sample = ""
                if finding.get("feature_indexes"):
                    sample = f"; sample feature indexes: {finding['feature_indexes']}"
                lines.append(
                    f"  - **{finding['severity'].upper()}** {inline_code(finding['code'], quote_strings=False)}"
                    f"{suffix}: {finding['message']} Count: {finding['occurrence_count']}{sample}"
                )
        else:
            lines.append("- Findings: none")
        lines.append("")

    lines.extend(["## Remaining execution-time checks", ""])
    for message in report.get("remaining_checks", []):
        lines.append(f"- {message}")
    lines.extend(
        [
            "",
            "## Evidence",
            "",
            f"- Workflow digest: {inline_code(report['workflow_digest'], quote_strings=False)}",
            f"- Contract digest: {inline_code(report['contract_digest'], quote_strings=False)}",
            f"- Preflight digest: {inline_code(report['preflight_digest'], quote_strings=False)}",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "WORKFLOW_PREFLIGHT_VERSION",
    "WorkflowPreflight",
    "preflight_workflow_inputs",
    "render_workflow_preflight_markdown",
]
