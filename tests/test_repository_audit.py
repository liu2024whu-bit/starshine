from __future__ import annotations

from pathlib import Path

from scripts.audit_public_repository import (
    _documentation_index_violations,
    _workflow_pipeline_violations,
)


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

def test_workflow_pipeline_audit_accepts_pipefail_guarded_tee(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    _write(
        workflows / "ci.yml",
        """name: CI
jobs:
  test:
    steps:
      - name: Run tests
        shell: bash
        run: |
          set -o pipefail
          python -m pytest 2>&1 | tee pytest.log
""",
    )

    assert _workflow_pipeline_violations(workflows) == []


def test_workflow_pipeline_audit_rejects_unguarded_tee(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    _write(
        workflows / "ci.yml",
        """name: CI
jobs:
  build:
    steps:
      - name: Inspect artifacts
        run: >-
          python scripts/check_release_artifacts.py dist
          2>&1 | tee release-artifact-check.log
""",
    )

    assert _workflow_pipeline_violations(workflows) == [
        f"workflow tee pipeline lacks pipefail: {(workflows / 'ci.yml').as_posix()}:6"
    ]


def test_workflow_pipeline_audit_ignores_run_blocks_without_tee(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    _write(
        workflows / "latest.yml",
        """name: Latest
jobs:
  test:
    steps:
      - run: python -m pytest
""",
    )

    assert _workflow_pipeline_violations(workflows) == []

