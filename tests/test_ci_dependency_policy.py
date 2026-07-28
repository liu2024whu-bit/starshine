from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSTRAINTS_PATH = ROOT / "requirements" / "ci-validation.txt"
MAIN_CI_PATH = ROOT / ".github" / "workflows" / "ci.yml"
LATEST_CI_PATH = ROOT / ".github" / "workflows" / "latest-compatible.yml"
EXPECTED_TOOLS = {"ruff", "pytest", "jsonschema", "build", "twine"}
PIN_PATTERN = re.compile(
    r"(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[0-9][A-Za-z0-9_.!+-]*)"
)


def _constraint_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw_line in CONSTRAINTS_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_PATTERN.fullmatch(line)
        assert match is not None, f"CI constraint must be an exact direct pin: {line}"
        name = match.group("name").lower().replace("_", "-")
        assert name not in pins, f"duplicate CI constraint: {name}"
        pins[name] = match.group("version")
    return pins


def test_ci_constraints_pin_only_the_reviewed_validation_tools():
    pins = _constraint_pins()
    assert set(pins) == EXPECTED_TOOLS
    assert all(version for version in pins.values())


def test_normal_ci_constrains_every_editable_validation_install():
    workflow = MAIN_CI_PATH.read_text(encoding="utf-8")
    install_lines = [
        line.strip()
        for line in workflow.splitlines()
        if "python -m pip install" in line
        and (".[dev" in line or ".[release]" in line)
    ]

    assert install_lines
    assert all(
        "--constraint requirements/ci-validation.txt" in line
        for line in install_lines
    )


def test_latest_compatible_workflow_remains_unconstrained_and_scheduled():
    workflow = LATEST_CI_PATH.read_text(encoding="utf-8")

    assert "schedule:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "--constraint" not in workflow
    assert '.[dev]' in workflow
    assert '.[release]' in workflow
