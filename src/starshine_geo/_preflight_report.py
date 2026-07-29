from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from pyproj import CRS

from ._preflight_checks import check_layer_use, summarize_layer
from ._preflight_findings import _FindingCollector
from ._preflight_model import (
    REMAINING_CHECKS,
    WORKFLOW_PREFLIGHT_VERSION,
    WorkflowPreflight,
)
from .contracts import build_workflow_contract
from .geojson import FeatureCollection
from .manifest import digest_json


def build_workflow_preflight_report(
    workflow: dict[str, Any],
    layers: Mapping[str, FeatureCollection],
) -> WorkflowPreflight:
    """Assemble a deterministic report from contracts and external-layer checks."""
    contract = build_workflow_contract(workflow, layers.keys())
    findings = _FindingCollector()
    summaries: list[dict[str, Any]] = []
    validated_layers: dict[str, FeatureCollection] = {}
    declared_crs_by_layer: dict[str, CRS | None] = {}
    layer_contracts = {layer["name"]: layer for layer in contract["layers"]}

    for layer_contract in contract["layers"]:
        name = layer_contract["name"]
        summary, validated, declared_crs = summarize_layer(
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

        for use in layer_contract["uses"]:
            use_key = (use["step_index"], use["input_name"])
            layer_by_use[use_key] = layer_name
            effective_crs_by_use[use_key] = check_layer_use(
                layer_name=layer_name,
                use=use,
                collection=validated,
                declared_crs=declared_crs_by_layer[layer_name],
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
            if (
                current_crs is not None
                and other_crs is not None
                and not current_crs.equals(other_crs)
            ):
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
        "remaining_checks": list(REMAINING_CHECKS),
    }
    report["preflight_digest"] = digest_json(report)
    return report


__all__ = ["build_workflow_preflight_report"]
