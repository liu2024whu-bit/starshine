from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote, urlsplit

from ._version import package_version
from .errors import ValidationError
from .manifest import digest_json
from .preflight import WORKFLOW_PREFLIGHT_VERSION, WorkflowPreflight

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA_URI = "https://json.schemastore.org/sarif-2.1.0.json"
_TOOL_NAME = "Starshine Geo Workflow Preflight"
_INFORMATION_URI = "https://github.com/liu2024whu-bit/starshine"
_LEVELS = {"error": "error", "warning": "warning"}
_LEVEL_RANK = {"warning": 0, "error": 1}

WorkflowPreflightSarif = dict[str, Any]


def _is_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_report(report: WorkflowPreflight) -> list[dict[str, Any]]:
    if not isinstance(report, dict) or report.get("schema_version") != WORKFLOW_PREFLIGHT_VERSION:
        raise ValidationError("workflow preflight report must use schema version 1")
    findings = report.get("findings")
    if not isinstance(findings, list):
        raise ValidationError("workflow preflight report must contain a findings array")

    for digest_name in ("workflow_digest", "contract_digest", "preflight_digest"):
        if not isinstance(report.get(digest_name), str) or not report[digest_name]:
            raise ValidationError(f"workflow preflight report must contain {digest_name}")
    if not isinstance(report.get("valid"), bool):
        raise ValidationError("workflow preflight report must contain a boolean valid value")
    for count_name in ("error_count", "warning_count"):
        if not _is_non_negative_int(report.get(count_name)):
            raise ValidationError(f"workflow preflight report must contain {count_name}")

    validated: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValidationError("workflow preflight findings must be objects")
        required = ("severity", "code", "message", "layer", "occurrence_count")
        if any(key not in finding for key in required):
            raise ValidationError("workflow preflight findings are missing required fields")
        if finding["severity"] not in _LEVELS:
            raise ValidationError(f"unsupported workflow preflight severity: {finding['severity']}")
        text_fields = ("code", "message", "layer")
        if not all(isinstance(finding[key], str) and finding[key] for key in text_fields):
            raise ValidationError("workflow preflight finding text fields must be non-empty strings")
        occurrence_count = finding["occurrence_count"]
        if not _is_non_negative_int(occurrence_count) or occurrence_count < 1:
            raise ValidationError("workflow preflight occurrence counts must be positive integers")

        if "step_index" in finding and not _is_non_negative_int(finding["step_index"]):
            raise ValidationError("workflow preflight step indexes must be non-negative integers")
        for key in ("operation", "input_name", "field"):
            if key in finding and (not isinstance(finding[key], str) or not finding[key]):
                raise ValidationError(f"workflow preflight {key} values must be non-empty strings")
        if "feature_indexes" in finding:
            indexes = finding["feature_indexes"]
            if (
                not isinstance(indexes, list)
                or not indexes
                or any(not _is_non_negative_int(index) for index in indexes)
                or len(set(indexes)) != len(indexes)
                or len(indexes) > occurrence_count
            ):
                raise ValidationError(
                    "workflow preflight feature indexes must be unique non-negative samples"
                )
        validated.append(finding)
    return validated


def _normalize_uri(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("SARIF artifact URIs must be non-empty strings")
    normalized = value.strip().replace("\\", "/")
    if any(ord(character) < 32 for character in normalized):
        raise ValidationError("SARIF artifact URIs must not contain control characters")
    if normalized.startswith("/") or urlsplit(normalized).scheme:
        raise ValidationError("SARIF artifact URIs must be repository-relative")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    path = PurePosixPath(normalized)
    if not normalized or path.as_posix() == "." or ".." in path.parts:
        raise ValidationError("SARIF artifact URIs must remain inside the repository root")
    return quote(path.as_posix(), safe="/-._~")


def _artifact_uris(
    findings: list[dict[str, Any]],
    artifact_uris: Mapping[str, str],
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for name, uri in artifact_uris.items():
        if not isinstance(name, str) or not name:
            raise ValidationError("SARIF artifact URI layer names must be non-empty strings")
        normalized[name] = _normalize_uri(uri)
    missing = sorted({finding["layer"] for finding in findings} - set(normalized))
    if missing:
        raise ValidationError(f"SARIF artifact URI is missing for layer: {missing[0]}")
    return normalized


def _rule_id(code: str) -> str:
    return f"starshine.preflight.{code}"


def _rule_name(code: str) -> str:
    return " ".join(part for part in code.replace("-", "_").split("_") if part).title()


def _rules(findings: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_code: dict[str, dict[str, Any]] = {}
    for finding in findings:
        code = finding["code"]
        current = by_code.get(code)
        if current is None or _LEVEL_RANK[finding["severity"]] > _LEVEL_RANK[current["severity"]]:
            by_code[code] = finding

    rules: list[dict[str, Any]] = []
    indexes: dict[str, int] = {}
    for code in sorted(by_code):
        finding = by_code[code]
        indexes[code] = len(rules)
        rules.append(
            {
                "id": _rule_id(code),
                "name": _rule_name(code),
                "shortDescription": {"text": _rule_name(code)},
                "fullDescription": {"text": finding["message"]},
                "defaultConfiguration": {"level": _LEVELS[finding["severity"]]},
                "properties": {
                    "tags": ["correctness", "geospatial", "workflow-preflight"],
                    "precision": "high",
                },
            }
        )
    return rules, indexes


def _message(finding: dict[str, Any]) -> str:
    context = [f"Layer {finding['layer']}"]
    if "step_index" in finding:
        context.append(f"step {finding['step_index']}")
    if "operation" in finding:
        context.append(f"operation {finding['operation']}")
    if "input_name" in finding:
        context.append(f"input {finding['input_name']}")
    if "field" in finding:
        context.append(f"field {finding['field']}")
    context.append(f"occurrences {finding['occurrence_count']}")
    if finding.get("feature_indexes"):
        context.append(f"sample feature indexes {finding['feature_indexes']}")
    return f"{finding['message']} ({'; '.join(context)})."


def _logical_locations(finding: dict[str, Any]) -> list[dict[str, Any]]:
    locations = [
        {
            "name": finding["layer"],
            "fullyQualifiedName": f"layer:{finding['layer']}",
            "kind": "module",
        }
    ]
    if "step_index" in finding:
        operation = finding.get("operation", "workflow operation")
        locations.append(
            {
                "name": f"step {finding['step_index']}: {operation}",
                "fullyQualifiedName": f"workflow.step[{finding['step_index']}]:{operation}",
                "kind": "function",
            }
        )
    if "input_name" in finding:
        locations.append(
            {
                "name": finding["input_name"],
                "fullyQualifiedName": f"workflow.input:{finding['input_name']}",
                "kind": "parameter",
            }
        )
    if "field" in finding:
        locations.append(
            {
                "name": finding["field"],
                "fullyQualifiedName": f"property:{finding['field']}",
                "kind": "member",
            }
        )
    return locations


def _fingerprint(finding: dict[str, Any]) -> str:
    identity = {
        key: deepcopy(finding[key])
        for key in (
            "code",
            "layer",
            "step_index",
            "operation",
            "input_name",
            "field",
        )
        if key in finding
    }
    return digest_json(identity).removeprefix("sha256:")


def _result(
    finding: dict[str, Any],
    *,
    artifact_uri: str,
    rule_index: int,
) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "layer": finding["layer"],
        "occurrenceCount": finding["occurrence_count"],
    }
    for source, target in (
        ("step_index", "stepIndex"),
        ("operation", "operation"),
        ("input_name", "inputName"),
        ("field", "field"),
        ("feature_indexes", "sampleFeatureIndexes"),
    ):
        if source in finding:
            properties[target] = deepcopy(finding[source])

    return {
        "ruleId": _rule_id(finding["code"]),
        "ruleIndex": rule_index,
        "level": _LEVELS[finding["severity"]],
        "message": {"text": _message(finding)},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": artifact_uri,
                        "uriBaseId": "%SRCROOT%",
                    },
                    "region": {"startLine": 1},
                },
                "logicalLocations": _logical_locations(finding),
            }
        ],
        "partialFingerprints": {"starshinePreflight/v1": _fingerprint(finding)},
        "properties": properties,
    }


def build_workflow_preflight_sarif(
    report: WorkflowPreflight,
    artifact_uris: Mapping[str, str],
    *,
    automation_id: str = "starshine/preflight/",
) -> WorkflowPreflightSarif:
    """Convert a completed Workflow Preflight v1 report to deterministic SARIF 2.1.0.

    The converter does not inspect data, rebuild a contract, or execute workflow operators. Artifact
    URIs are supplied explicitly so callers control repository-relative locations while the canonical
    preflight report remains path-free.
    """
    findings = _validate_report(report)
    if not isinstance(artifact_uris, Mapping):
        raise ValidationError("SARIF artifact URIs must be supplied as a mapping")
    normalized_uris = _artifact_uris(findings, artifact_uris)
    if not isinstance(automation_id, str) or not automation_id.strip():
        raise ValidationError("SARIF automation identifier must be a non-empty string")
    normalized_automation_id = automation_id.strip().replace("\\", "/")
    if any(ord(character) < 32 for character in normalized_automation_id):
        raise ValidationError("SARIF automation identifier must not contain control characters")
    if not normalized_automation_id.endswith("/"):
        normalized_automation_id += "/"

    rules, rule_indexes = _rules(findings)
    results = [
        _result(
            finding,
            artifact_uri=normalized_uris[finding["layer"]],
            rule_index=rule_indexes[finding["code"]],
        )
        for finding in findings
    ]
    return {
        "$schema": SARIF_SCHEMA_URI,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": _TOOL_NAME,
                        "informationUri": _INFORMATION_URI,
                        "semanticVersion": package_version(),
                        "rules": rules,
                    }
                },
                "automationDetails": {"id": normalized_automation_id},
                "invocations": [{"executionSuccessful": True}],
                "results": results,
                "properties": {
                    "workflowDigest": report.get("workflow_digest"),
                    "contractDigest": report.get("contract_digest"),
                    "preflightDigest": report["preflight_digest"],
                    "valid": bool(report.get("valid")),
                    "errorCount": report.get("error_count"),
                    "warningCount": report.get("warning_count"),
                },
            }
        ],
    }


__all__ = [
    "SARIF_SCHEMA_URI",
    "SARIF_VERSION",
    "WorkflowPreflightSarif",
    "build_workflow_preflight_sarif",
]
