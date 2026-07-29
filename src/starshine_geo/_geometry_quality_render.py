from __future__ import annotations

from ._geometry_quality_model import GeometryQualityReport
from ._markdown import inline_code
from .errors import ValidationError


def _validate_report_for_render(report: GeometryQualityReport) -> None:
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise ValidationError("geometry quality report must use schema version 1")
    if not isinstance(report.get("findings"), list):
        raise ValidationError("geometry quality report must contain a findings array")
    if not isinstance(report.get("geometry_counts"), dict):
        raise ValidationError("geometry quality report must contain geometry counts")
    digest_status = report.get("collection_digest_status")
    collection_digest = report.get("collection_digest")
    if digest_status not in {"available", "unavailable"}:
        raise ValidationError("geometry quality report must contain a collection digest status")
    if digest_status == "available" and not isinstance(collection_digest, str):
        raise ValidationError("available collection digests must be strings")
    if digest_status == "unavailable" and collection_digest is not None:
        raise ValidationError("unavailable collection digests must be null")


def render_geometry_quality_report(report: GeometryQualityReport) -> str:
    """Render a deterministic Markdown geometry-quality report."""
    _validate_report_for_render(report)
    status = "PASS" if report["valid"] else "FAIL"
    lines = [
        "# Starshine Geometry Quality Report",
        "",
        f"- Status: **{status}**",
        f"- Features: {report['feature_count']}",
        f"- Parsed geometries: {report['parsed_geometry_count']}",
        f"- Valid geometries: {report['valid_geometry_count']}",
        f"- Invalid geometry entries: {report['invalid_geometry_count']}",
        f"- Errors: {report['error_count']}",
        f"- Warnings: {report['warning_count']}",
        f"- Declared CRS: {inline_code(report['declared_crs'])}",
        f"- CRS status: {report['crs_status']}",
        "",
        "## Geometry structure",
        "",
    ]

    if report["geometry_counts"]:
        for geometry_type, count in report["geometry_counts"].items():
            lines.append(f"- {inline_code(geometry_type, quote_strings=False)}: {count}")
    else:
        lines.append("- Parsed geometry types: none")
    lines.extend(
        [
            f"- Total coordinate positions: {report['total_coordinate_count']}",
            f"- Maximum coordinate positions in one feature: {report['max_coordinate_count']}",
            f"- Duplicate geometry groups: {report['duplicate_geometry_group_count']}",
            f"- Features in duplicate groups: {report['duplicate_feature_count']}",
            "",
            "## Coordinate dimensions",
            "",
        ]
    )
    for label, count in report["coordinate_dimension_counts"].items():
        lines.append(f"- {label}: {count}")

    lines.extend(["", "## Findings", ""])
    if not report["findings"]:
        lines.append("- None")
    else:
        for finding in report["findings"]:
            context = ""
            if finding.get("geometry_type"):
                geometry_type = inline_code(finding["geometry_type"], quote_strings=False)
                context = f" ({geometry_type})"
            sample = ""
            if finding.get("feature_indexes"):
                sample = f"; sample feature indexes: {finding['feature_indexes']}"
            severity = finding["severity"].upper()
            code = inline_code(finding["code"], quote_strings=False)
            lines.append(
                f"- **{severity}** {code}{context}: {finding['message']} "
                f"Count: {finding['occurrence_count']}{sample}"
            )

    lines.extend(
        [
            "",
            "## Evidence",
            "",
            f"- Collection digest status: {report['collection_digest_status']}",
            f"- Collection digest: {inline_code(report['collection_digest'], quote_strings=False)}",
            f"- Quality digest: {inline_code(report['quality_digest'], quote_strings=False)}",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = ["render_geometry_quality_report"]
