from __future__ import annotations

import html
import json
import re
from typing import Any


def _single_line(text: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", " ", " ".join(text.splitlines()))


def plain_text(value: str) -> str:
    """Keep externally derived diagnostic prose literal in a report list item."""
    text = html.escape(_single_line(value), quote=False)
    return re.sub(r"([\\`*_\[\]#|~])", r"\\\1", text)


def inline_code(value: Any, *, quote_strings: bool = True) -> str:
    """Render inline code for report headings and lists (not GFM table cells).

    Line breaks and remaining ASCII controls become spaces. Empty raw strings
    use the explicit JSON spelling ``""``. Backticks use a longer delimiter,
    since backslash escapes are not interpreted inside CommonMark code spans.
    Literal pipes are preserved; table renderers need a separate cell policy.
    """
    if isinstance(value, str) and not quote_strings:
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    text = _single_line(text)
    if not text:
        text = '""'
    delimiter = "`" * (1 + max((len(run) for run in re.findall(r"`+", text)), default=0))
    # CommonMark strips one surrounding space when the content is not all spaces.
    # Padding also separates boundary backticks from the opening/closing delimiter.
    if text.startswith("`") or text.endswith("`") or (
        text.startswith(" ") and text.endswith(" ") and text.strip(" ")
    ):
        text = f" {text} "
    return f"{delimiter}{text}{delimiter}"


__all__ = ["inline_code", "plain_text"]
