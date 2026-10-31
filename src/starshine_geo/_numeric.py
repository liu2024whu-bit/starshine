from __future__ import annotations

import math
from typing import Any


def is_finite_number(value: Any) -> bool:
    """Whether a JSON number can safely enter double-precision geometry operations."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False
