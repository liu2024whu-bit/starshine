from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath

_MAX_TRACKED_BYTES = 2 * 1024 * 1024
_PRIVATE_ORIGIN = "supermap-team/" + "chaotu"
_PRIVATE_ORIGIN_ALLOWLIST = {"docs/PROJECT_HISTORY.md"}
_FORBIDDEN_SUFFIXES = {
    ".7z",
    ".db",
    ".docx",
    ".gpkg",
    ".pdf",
    ".shp",
    ".sqlite",
    ".tif",
    ".tiff",
    ".xlsx",
    ".zip",
}
_FORBIDDEN_PATH_PARTS = {
    ".env",
    ".pytest_cache",
    "__pycache__",
    "archive",
    "ocr",
    "runtime_outputs",
}
_SECRET_PATTERNS = {
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "OpenAI-style secret": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
_ABSOLUTE_PATH_PATTERNS = {
    "Unix home path": re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/"),
    "Windows user path": re.compile(r"[A-Za-z]:[\\/](?:Users|home)[\\/]"),
}
_MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [Path(item.decode("utf-8")) for item in result.stdout.split(b"\0") if item]


def _is_test_path(path: Path) -> bool:
    return PurePosixPath(path.as_posix()).parts[:1] == ("tests",)


def _local_markdown_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    target = target.split("#", 1)[0].split("?", 1)[0]
    return target or None


def _documentation_index_violations(docs_root: Path = Path("docs")) -> list[str]:
    """Check that the documentation index owns every top-level Markdown document."""
    index = docs_root / "README.md"
    if not index.is_file():
        return ["documentation index is missing: docs/README.md"]

    root = docs_root.resolve()
    index_text = index.read_text(encoding="utf-8")
    referenced_top_level: set[str] = set()
    violations: list[str] = []

    for match in _MARKDOWN_LINK_PATTERN.finditer(index_text):
        target = _local_markdown_target(match.group(1))
        if target is None:
            continue

        resolved = (docs_root / target).resolve(strict=False)
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            violations.append(f"documentation index link escapes docs/: {target}")
            continue

        if not resolved.exists():
            violations.append(f"documentation index link is missing: docs/{relative.as_posix()}")
            continue

        if resolved.is_file() and resolved.suffix.casefold() == ".md" and resolved.parent == root:
            referenced_top_level.add(resolved.name)

    top_level_docs = {
        path.name
        for path in docs_root.glob("*.md")
        if path.is_file() and path.name != "README.md"
    }
    for name in sorted(top_level_docs - referenced_top_level):
        violations.append(f"top-level documentation is not indexed: docs/{name}")

    return violations


def audit() -> list[str]:
    """Return public-boundary violations for tracked repository files."""
    violations: list[str] = []
    for path in _tracked_files():
        normalized = path.as_posix()
        parts = set(PurePosixPath(normalized).parts)

        if path.suffix.casefold() in _FORBIDDEN_SUFFIXES:
            violations.append(f"forbidden tracked artifact type: {normalized}")
        if parts & _FORBIDDEN_PATH_PARTS:
            violations.append(f"forbidden tracked path segment: {normalized}")
        if not path.is_file():
            continue

        size = path.stat().st_size
        if size > _MAX_TRACKED_BYTES:
            violations.append(f"tracked file exceeds 2 MiB public limit: {normalized} ({size} bytes)")

        payload = path.read_bytes()
        if b"\0" in payload:
            continue
        text = payload.decode("utf-8", errors="replace")

        if _PRIVATE_ORIGIN in text and normalized not in _PRIVATE_ORIGIN_ALLOWLIST:
            violations.append(
                f"private-origin identifier is only allowed in provenance documentation: {normalized}"
            )
        for name, pattern in _SECRET_PATTERNS.items():
            if pattern.search(text):
                violations.append(f"possible {name} in tracked file: {normalized}")
        if not _is_test_path(path):
            for name, pattern in _ABSOLUTE_PATH_PATTERNS.items():
                if pattern.search(text):
                    violations.append(f"possible {name} outside tests: {normalized}")

    violations.extend(_documentation_index_violations())
    return violations


def main() -> int:
    violations = audit()
    if violations:
        print("Public repository audit failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print("Public repository audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
