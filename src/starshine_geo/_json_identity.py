from __future__ import annotations

import json
from typing import Any


def json_unique_key(value: Any) -> tuple[str, str] | None:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError):
        return None
    return type(value).__name__, payload
