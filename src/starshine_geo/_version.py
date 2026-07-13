from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

_PACKAGE_NAME = "starshine-geo"


def package_version() -> str:
    """Return the installed package version without duplicating release metadata."""
    try:
        return version(_PACKAGE_NAME)
    except PackageNotFoundError:
        return "0+unknown"


__version__ = package_version()
