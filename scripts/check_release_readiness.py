from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised only on Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).parents[1]
_STABLE_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_DEVELOPMENT_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)\.dev(\d+)$")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _field(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s*[\"']?([^\"'\n]+)[\"']?\s*$", text, re.MULTILINE)
    if match is None:
        raise RuntimeError(f"CITATION.cff is missing {name}")
    return match.group(1).strip()


def _stable_tuple(version: str) -> tuple[int, int, int]:
    match = _STABLE_VERSION.fullmatch(version)
    if match is None:
        raise RuntimeError(f"expected stable X.Y.Z version, got: {version}")
    return tuple(int(value) for value in match.groups())


def check(root: Path = ROOT, *, require_release: bool = False) -> dict[str, Any]:
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(metadata["project"]["version"])

    citation = (root / "CITATION.cff").read_text(encoding="utf-8")
    release_version = _field(citation, "version")
    release_date = _field(citation, "date-released")
    _require(
        _STABLE_VERSION.fullmatch(release_version) is not None,
        "citation version must identify a stable X.Y.Z release",
    )
    _require(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}", release_date) is not None,
        "citation release date must use YYYY-MM-DD",
    )

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    _require("## [Unreleased]" in changelog, "changelog is missing the Unreleased section")
    release_heading = f"## [{release_version}] - {release_date}"
    _require(
        release_heading in changelog,
        f"changelog is missing latest stable release heading: {release_heading}",
    )

    notes_path = root / "docs" / "releases" / f"{release_version}.md"
    _require(
        notes_path.is_file(),
        f"missing latest stable release notes: {notes_path.relative_to(root)}",
    )
    notes = notes_path.read_text(encoding="utf-8")
    _require(
        notes.startswith(f"# Starshine Geo {release_version}\n"),
        "latest stable release notes title does not match CITATION.cff",
    )

    readme = (root / "README.md").read_text(encoding="utf-8")
    _require(
        f"[{release_version} release notes](docs/releases/{release_version}.md)" in readme,
        "README does not link the latest stable release notes",
    )

    stable_match = _STABLE_VERSION.fullmatch(version)
    development_match = _DEVELOPMENT_VERSION.fullmatch(version)

    if stable_match is not None:
        _require(
            release_version == version,
            "stable project version does not match CITATION.cff",
        )
        _require(
            f"status-{version}%20research%20preview" in readme,
            "README stable status badge does not match the project version",
        )
        _require(
            f"Starshine Geo {version} is an alpha-quality research preview." in readme,
            "README stable project status does not match the project version",
        )
        mode = "release"
    elif development_match is not None:
        _require(
            not require_release,
            "project.version is a development snapshot; set a stable version before release",
        )
        development_base = ".".join(development_match.groups()[:3])
        _require(
            _stable_tuple(development_base) > _stable_tuple(release_version),
            "development version must target a release newer than CITATION.cff",
        )
        _require(
            f"status-{version}%20development%20snapshot" in readme,
            "README development status badge does not match the project version",
        )
        _require(
            f"Starshine Geo {version} is the current development snapshot." in readme,
            "README development project status does not match the project version",
        )
        _require(
            f"The latest stable release metadata remains {release_version}." in readme,
            "README does not distinguish the development snapshot from the latest stable release",
        )
        mode = "development"
    else:
        raise RuntimeError(
            "project.version must be stable X.Y.Z or a supported X.Y.Z.devN development snapshot"
        )

    if require_release:
        _require(mode == "release", "release mode requires stable project metadata")

    return {
        "version": version,
        "mode": mode,
        "release_version": release_version,
        "release_date": release_date,
        "release_notes": str(notes_path.relative_to(root)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check Starshine development/release metadata consistency"
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--require-release",
        action="store_true",
        help="reject development snapshot versions when preparing a tagged release",
    )
    args = parser.parse_args(argv)
    summary = check(args.root, require_release=args.require_release)

    if summary["mode"] == "release":
        print(
            "Release metadata is consistent for "
            f"Starshine Geo {summary['version']} ({summary['release_date']})."
        )
    else:
        print(
            "Development metadata is consistent for "
            f"Starshine Geo {summary['version']}; latest stable release metadata is "
            f"{summary['release_version']} ({summary['release_date']})."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
