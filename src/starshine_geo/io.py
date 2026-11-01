from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import ValidationError

JsonObject = dict[str, Any]


def read_json(path: str | Path) -> JsonObject:
    source = Path(path)
    try:
        if not source.is_file():
            raise ValidationError(f"File not found: {source}")
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        # Parser/encoding exception text may contain private input excerpts.
        raise ValidationError(f"Cannot read JSON from {source}") from exc
    if not isinstance(value, dict):
        raise ValidationError("Top-level JSON value must be an object")
    return value


def write_text(content: str, path: str | Path) -> Path:
    """Write UTF-8 text, validating encoding before opening the destination."""
    destination = Path(path)
    try:
        content.encode("utf-8")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise ValidationError(f"Cannot write text to {destination}") from exc
    return destination


def prepare_json_text(value: JsonObject, path: str | Path) -> str:
    """Serialize and validate UTF-8 before any destination is opened."""
    try:
        content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        content.encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValidationError(f"Cannot serialize JSON for {path}") from exc
    return content


def write_json(value: JsonObject, path: str | Path) -> Path:
    destination = Path(path)
    return write_text(prepare_json_text(value, destination), destination)
