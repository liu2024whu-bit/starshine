from __future__ import annotations

from pathlib import Path

from .errors import ValidationError


def same_file(left: Path, right: Path) -> bool:
    """Compare path aliases, including existing hard links, before writing.

    Missing distinct paths are allowed. Other filesystem failures fail closed.
    This check does not prevent concurrent filesystem changes after validation.
    """
    try:
        if left.resolve(strict=False) == right.resolve(strict=False):
            return True
        try:
            return left.samefile(right)
        except FileNotFoundError:
            return False
    except (OSError, RuntimeError) as exc:
        raise ValidationError("cannot safely compare output and protected file paths") from exc
