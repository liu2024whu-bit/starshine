from __future__ import annotations

from pathlib import Path

from scripts.audit_public_repository import _documentation_index_violations


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_documentation_index_accepts_owned_top_level_pages(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    _write(
        docs / "README.md",
        "# Docs\n\n- [Architecture](ARCHITECTURE.md)\n- [Release notes](releases/)\n",
    )
    _write(docs / "ARCHITECTURE.md", "# Architecture\n")
    (docs / "releases").mkdir()

    assert _documentation_index_violations(docs) == []


def test_documentation_index_rejects_orphan_top_level_page(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    _write(docs / "README.md", "# Docs\n\n- [Architecture](ARCHITECTURE.md)\n")
    _write(docs / "ARCHITECTURE.md", "# Architecture\n")
    _write(docs / "PARALLEL_GUIDE.md", "# Parallel guide\n")

    assert _documentation_index_violations(docs) == [
        "top-level documentation is not indexed: docs/PARALLEL_GUIDE.md"
    ]


def test_documentation_index_rejects_missing_and_escaping_links(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    _write(
        docs / "README.md",
        "# Docs\n\n- [Missing](MISSING.md)\n- [Escape](../PRIVATE.md)\n",
    )

    assert _documentation_index_violations(docs) == [
        "documentation index link is missing: docs/MISSING.md",
        "documentation index link escapes docs/: ../PRIVATE.md",
    ]


def test_documentation_index_ignores_external_and_anchor_links(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    _write(
        docs / "README.md",
        "# Docs\n\n- [Web](https://example.com/docs)\n- [Section](#maintenance)\n",
    )

    assert _documentation_index_violations(docs) == []
