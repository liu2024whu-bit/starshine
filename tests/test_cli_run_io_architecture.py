from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "starshine_geo"


def _module_tree(module: str) -> ast.Module:
    return ast.parse((PACKAGE_ROOT / f"{module}.py").read_text(encoding="utf-8"))


def _relative_imports(module: str) -> set[str]:
    return {
        node.module
        for node in ast.walk(_module_tree(module))
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module
    }


def _absolute_import_roots(module: str) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(_module_tree(module)):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module.split(".", 1)[0])
    return imports


def _function_names(module: str) -> set[str]:
    return {
        node.name
        for node in ast.walk(_module_tree(module))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
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


def test_cli_binding_boundary_has_no_pre_unification_shims():
    assert {"_parse_layer_bindings", "_parse_layers"}.isdisjoint(_function_names("cli"))
    assert "prepare_preflight_layer_bindings" not in _function_names("_cli_layer_sources")
    assert "prepare_layer_bindings" in _function_names("_cli_layer_sources")


def test_source_metadata_dependency_boundary_is_one_way():
    inventory_imports = _relative_imports("inventory")
    assert {"errors", "geojson", "io"}.issubset(inventory_imports)

    forbidden = {
        "_cli_layer_sources",
        "_cli_run_output",
        "cli",
        "contracts",
        "doctor",
        "explain",
        "geopackage",
        "graph",
        "inspection",
        "manifest",
        "metrics",
        "operator_registry",
        "operators",
        "planning",
        "preflight",
        "preflight_sarif",
        "workflow",
    }
    assert inventory_imports.isdisjoint(forbidden)
    assert {"pyogrio", "geopandas"}.isdisjoint(_absolute_import_roots("inventory"))
    assert "inventory" not in _relative_imports("inspection")

    for module in (
        "contracts",
        "operator_registry",
        "operators",
        "planning",
        "preflight",
        "preflight_sarif",
        "workflow",
    ):
        assert "inventory" not in _relative_imports(module)
