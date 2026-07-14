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


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _field(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s*[\"']?([^\"'\n]+)[\"']?\s*$", text, re.MULTILINE)
    if match is None:
        raise RuntimeError(f"CITATION.cff is missing {name}")
    return match.group(1).strip()


def check(root: Path = ROOT) -> dict[str, Any]:
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(metadata["project"]["version"])

    citation = (root / "CITATION.cff").read_text(encoding="utf-8")
    citation_version = _field(citation, "version")
    release_date = _field(citation, "date-released")
    _require(citation_version == version, "citation version does not match pyproject.toml")
    _require(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}", release_date) is not None,
        "citation release date must use YYYY-MM-DD",
    )

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = f"## [{version}] - {release_date}"
    _require(heading in changelog, f"changelog is missing current release heading: {heading}")
    _require("## [Unreleased]" in changelog, "changelog is missing the Unreleased section")

    notes_path = root / "docs" / "releases" / f"{version}.md"
    _require(notes_path.is_file(), f"missing versioned release notes: {notes_path.relative_to(root)}")
    notes = notes_path.read_text(encoding="utf-8")
    _require(
        notes.startswith(f"# Starshine Geo {version}\n"),
        "release notes title does not match the current version",
    )

    readme = (root / "README.md").read_text(encoding="utf-8")
    _require(
        f"status-{version}%20research%20preview" in readme,
        "README status badge does not match the current version",
    )
    _require(
        f"[{version} release notes](docs/releases/{version}.md)" in readme,
        "README does not link the current versioned release notes",
    )
    _require(
        f"Starshine Geo {version} is an alpha-quality research preview." in readme,
        "README project status does not match the current version",
    )

    return {
        "version": version,
        "release_date": release_date,
        "release_notes": str(notes_path.relative_to(root)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check public Starshine release metadata consistency")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    summary = check(args.root)
    print(
        "Release metadata is consistent for "
        f"Starshine Geo {summary['version']} ({summary['release_date']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
