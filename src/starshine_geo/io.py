from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import ValidationError

JsonObject = dict[str, Any]


def read_json(path: str | Path) -> JsonObject:
    source = Path(path)
    if not source.is_file():
        raise ValidationError(f"File not found: {source}")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Cannot read JSON from {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError("Top-level JSON value must be an object")
    return value


def write_json(value: JsonObject, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination
