from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "starshine_geo"


def _relative_imports(module_name: str) -> set[str]:
    tree = ast.parse((PACKAGE_ROOT / f"{module_name}.py").read_text(encoding="utf-8"))
    return {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module
    }


def test_spatial_index_dependency_boundary_is_one_way():
    index_imports = _relative_imports("_spatial_index")
    assert index_imports == {"errors"}

    operator_imports = _relative_imports("operators")
    assert "_spatial_index" in operator_imports

    forbidden = {
        "cli",
        "contracts",
        "geopackage",
        "manifest",
        "operator_registry",
        "planning",
        "preflight",
        "preflight_sarif",
        "workflow",
    }
    assert index_imports.isdisjoint(forbidden)


def test_public_and_workflow_modules_do_not_import_spatial_index_internals():
    for module_name in (
        "__init__",
        "cli",
        "contracts",
        "operator_registry",
        "planning",
        "preflight",
        "preflight_sarif",
        "workflow",
    ):
        assert "_spatial_index" not in _relative_imports(module_name)
