from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "starshine_geo"


def _relative_imports(module: str) -> set[str]:
    tree = ast.parse((PACKAGE_ROOT / f"{module}.py").read_text(encoding="utf-8"))
    return {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module
    }


def test_cli_input_and_output_adapters_do_not_import_workflow_core():
    forbidden = {
        "contracts",
        "operator_registry",
        "operators",
        "planning",
        "preflight",
        "preflight_sarif",
        "workflow",
    }
    assert _relative_imports("_cli_layer_sources").isdisjoint(forbidden)
    assert _relative_imports("_cli_run_output").isdisjoint(forbidden)


def test_core_workflow_modules_do_not_import_cli_adapters():
    for module in ("workflow", "operators", "contracts", "planning", "preflight"):
        imports = _relative_imports(module)
        assert "_cli_layer_sources" not in imports
        assert "_cli_run_output" not in imports


def test_console_command_tree_has_one_package_entry_module():
    assert not (PACKAGE_ROOT / "entrypoint.py").exists()
    assert "inventory" in _relative_imports("cli")
    assert "cli" not in _relative_imports("inventory")
