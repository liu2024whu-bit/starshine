"""Optional HTTP adapter above the public Starshine Geo core."""

from __future__ import annotations

from typing import Any


def create_app() -> Any:
    """Create the optional FastAPI application without importing it for core-only users."""
    from .app import create_app as _create_app

    return _create_app()


__all__ = ["create_app"]
