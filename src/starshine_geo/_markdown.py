from __future__ import annotations

import json
from typing import Any


def inline_code(value: Any, *, quote_strings: bool = True) -> str:
    """Render a deterministic Markdown inline-code value with normalized user text."""
    if isinstance(value, str) and not quote_strings:
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    text = " ".join(text.splitlines()).replace("`", "\\`")
    return f"`{text}`"


__all__ = ["inline_code"]
