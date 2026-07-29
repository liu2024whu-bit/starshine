from __future__ import annotations

from typing import Any

from ._markdown import inline_code
from ._preflight_model import WorkflowPreflight
from .errors import ValidationError


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
                    input_name = inline_code(finding["input_name"], quote_strings=False)
                    context.append(f"input {input_name}")
                if "field" in finding:
                    context.append(f"field {inline_code(finding['field'], quote_strings=False)}")
                suffix = f" ({', '.join(context)})" if context else ""
                sample = ""
                if finding.get("feature_indexes"):
                    sample = f"; sample feature indexes: {finding['feature_indexes']}"
                severity = finding["severity"].upper()
                code = inline_code(finding["code"], quote_strings=False)
                lines.append(
                    f"  - **{severity}** {code}{suffix}: {finding['message']} "
                    f"Count: {finding['occurrence_count']}{sample}"
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


__all__ = ["render_workflow_preflight_markdown"]
