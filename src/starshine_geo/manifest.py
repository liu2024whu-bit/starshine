from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from copy import deepcopy
from typing import Any

from ._version import package_version
from .errors import ValidationError
from .geojson import FeatureCollection

_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "credential",
    "dsn",
    "password",
    "passwd",
    "private_key",
    "secret",
    "token",
)
_PATH_KEYS = {"directory", "dir", "file", "folder", "path"}
_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_URL_WITH_CREDENTIALS = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/@\s]+:[^/@\s]+@")


def canonical_json(value: Any) -> str:
    """Serialize JSON-compatible data deterministically for hashing."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValidationError("Cannot serialize canonical JSON") from exc


def digest_json(value: Any) -> str:
    """Return a prefixed SHA-256 digest for JSON-compatible data."""
    try:
        payload = canonical_json(value).encode("utf-8")
    except UnicodeError as exc:
        raise ValidationError("Cannot encode canonical JSON as UTF-8") from exc
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _is_sensitive_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _is_path_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return normalized in _PATH_KEYS or normalized.endswith("_path")


def _is_absolute_path(value: str) -> bool:
    return value.startswith(("/", "\\\\")) or bool(_WINDOWS_ABSOLUTE_PATH.match(value))


def _sanitize(value: Any, *, key: str | None = None) -> Any:
    if key is not None and _is_sensitive_key(key):
        return "<redacted>"
    if key is not None and _is_path_key(key):
        return "<redacted-path>"
    if isinstance(value, dict):
        return {
            str(item_key): _sanitize(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str) and (
        _is_absolute_path(value) or _URL_WITH_CREDENTIALS.match(value)
    ):
        return "<redacted>"
    return deepcopy(value)


def _safe_layer_name(name: str, *, kind: str, index: int) -> str:
    safe_name = _sanitize(name)
    if safe_name in {"<redacted>", "<redacted-path>"}:
        return f"<redacted-{kind}-layer-{index}>"
    return str(safe_name)


def _input_layer_names(names: Iterable[str]) -> dict[str, str]:
    """Allocate aliases without stealing literal names or other default aliases."""
    aliases = {
        name: _safe_layer_name(name, kind="input", index=index)
        for index, name in enumerate(sorted(names))
    }
    reserved = set(aliases.values())
    used = {name for name, alias in aliases.items() if name == alias}
    for name, alias in aliases.items():
        if name == alias:
            continue
        if alias in used:
            suffix = 1
            candidate = f"{alias[:-1]}-{suffix}>"
            while candidate in reserved:
                suffix += 1
                candidate = f"{alias[:-1]}-{suffix}>"
            aliases[name] = candidate
            reserved.add(candidate)
        used.add(aliases[name])
    return aliases


def _declared_crs(layer: FeatureCollection) -> str | None:
    crs = layer.get("starshine:crs")
    return crs if isinstance(crs, str) and crs.strip() else None


def build_manifest(
    workflow: dict[str, Any],
    input_layers: dict[str, FeatureCollection],
    *,
    output_layer_name: str,
    output_layer: FeatureCollection,
    starshine_version: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic, path-free reproducibility manifest.

    Raw feature content and CLI file paths are never copied into the manifest. Sensitive
    parameter values, path-like parameters, and unsafe layer names are redacted before
    workflow hashing and reporting.
    """
    safe_workflow = _sanitize(workflow)
    steps = safe_workflow.get("steps", [])
    input_names = _input_layer_names(input_layers)
    safe_input_layers = {
        input_names[name]: {
            "digest": digest_json(layer),
            "crs": _declared_crs(layer),
        }
        for name, layer in sorted(input_layers.items())
    }

    return {
        "manifest_version": 1,
        "starshine_version": starshine_version or package_version(),
        "workflow_version": safe_workflow.get("version"),
        "workflow_digest": digest_json(safe_workflow),
        "input_layers": safe_input_layers,
        "executed_steps": [
            {
                "index": index,
                "operation": step.get("operation"),
                "inputs": deepcopy(step.get("inputs", {})),
                "parameters": deepcopy(step.get("parameters", {})),
                "output": step.get("output"),
            }
            for index, step in enumerate(steps)
            if isinstance(step, dict)
        ],
        "output_layer": {
            "name": _safe_layer_name(output_layer_name, kind="output", index=0),
            "digest": digest_json(output_layer),
            "crs": _declared_crs(output_layer),
        },
    }


def verify_result_manifest(
    result: FeatureCollection, manifest: dict[str, Any]
) -> dict[str, Any]:
    """Check selected-output content/declared CRS only, not provenance or GIS correctness.

    Object-key order and JSON whitespace do not affect the canonical digest. Array
    order and numeric representations retain the existing digest_json semantics.
    No workflow execution, geometry validation, mutation, or file I/O occurs here.
    """
    if not isinstance(manifest, dict):
        raise ValidationError("Result manifest must be a JSON object")
    version = manifest.get("manifest_version")
    if isinstance(version, bool) or not isinstance(version, (int, float)) or version != 1:
        raise ValidationError("Result verification requires manifest version 1")
    output = manifest.get("output_layer")
    if not isinstance(output, dict):
        raise ValidationError("Result manifest requires an output_layer object")
    expected = output.get("digest")
    if not isinstance(expected, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", expected) is None:
        raise ValidationError("Result manifest requires a canonical SHA-256 output digest")
    if "crs" not in output or (
        output["crs"] is not None
        and (not isinstance(output["crs"], str) or not output["crs"].strip())
    ):
        raise ValidationError("Result manifest output CRS must be a non-empty string or null")
    if (
        not isinstance(result, dict)
        or result.get("type") != "FeatureCollection"
        or not isinstance(result.get("features"), list)
    ):
        raise ValidationError("Result must be a GeoJSON FeatureCollection object")
    try:
        # Reject unsupported JSON representations even in unverified manifest fields.
        canonical_json(manifest)
        actual = digest_json(result)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValidationError("Result and manifest must contain finite JSON values") from exc
    checks = {
        "content_digest": actual == expected,
        "declared_crs": _declared_crs(result) == output["crs"],
    }
    return {
        "scope": "selected_output_only",
        "matched": all(checks.values()),
        "checks": checks,
        "expected_digest": expected,
        "actual_digest": actual,
    }
