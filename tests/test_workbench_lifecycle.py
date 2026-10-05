"""Run browser orchestration regressions through the existing full-suite CI gate."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_workbench_async_evidence_lifecycle() -> None:
    node = shutil.which("node")
    assert node is not None, "Workbench behavior checks require Node, as does the Server CI job."
    result = subprocess.run(
        [node, "--experimental-vm-modules", "--test", str(ROOT / "tests/workbench_lifecycle.mjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
