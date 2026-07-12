from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from importlib.metadata import PackageNotFoundError, version
from typing import Any

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
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest_json(value: Any) -> str:
    """Return a prefixed SHA-256 digest for JSON-compatible data."""
    payload = canonical_json(value).encode("utf-8")
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


def _package_version() -> str:
    try:
        return version("starshine-geo")
    except PackageNotFoundError:
        return "0.1.0"


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
    parameter values and path-like parameters are redacted before workflow hashing and
    step reporting.
    """
    safe_workflow = _sanitize(workflow)
    steps = safe_workflow.get("steps", [])

    return {
        "manifest_version": 1,
        "starshine_version": starshine_version or _package_version(),
        "workflow_version": safe_workflow.get("version"),
        "workflow_digest": digest_json(safe_workflow),
        "input_layers": {
            name: {
                "digest": digest_json(layer),
                "crs": _declared_crs(layer),
            }
            for name, layer in sorted(input_layers.items())
        },
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
            "name": output_layer_name,
            "digest": digest_json(output_layer),
            "crs": _declared_crs(output_layer),
        },
    }
