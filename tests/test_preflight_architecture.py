from __future__ import annotations

import ast
import inspect
from pathlib import Path

from starshine_geo import preflight_workflow_inputs, render_workflow_preflight_markdown

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "starshine_geo"
PREFLIGHT_MODULES = {
    "preflight",
    "_preflight_checks",
    "_preflight_findings",
    "_preflight_model",
    "_preflight_render",
    "_preflight_report",
    "preflight_sarif",
}


def _tree(module_name: str) -> ast.Module:
    path = PACKAGE_ROOT / f"{module_name}.py"
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _relative_imports(module_name: str) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(_tree(module_name)):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
            imports.add(node.module)
    return imports


def _preflight_edges() -> dict[str, set[str]]:
    return {
        module: _relative_imports(module) & PREFLIGHT_MODULES
        for module in PREFLIGHT_MODULES
    }


def _assert_acyclic(edges: dict[str, set[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module: str) -> None:
        if module in visiting:
            raise AssertionError(f"circular Preflight dependency detected at {module}")
        if module in visited:
            return
        visiting.add(module)
        for dependency in edges[module]:
            visit(dependency)
        visiting.remove(module)
        visited.add(module)

    for module in edges:
        visit(module)


def test_public_preflight_facade_stays_small_and_preserves_callable_identity():
    facade_path = PACKAGE_ROOT / "preflight.py"
    assert len(facade_path.read_text(encoding="utf-8").splitlines()) <= 80
    assert preflight_workflow_inputs.__module__ == "starshine_geo.preflight"
    assert render_workflow_preflight_markdown.__module__ == "starshine_geo.preflight"
    assert list(inspect.signature(preflight_workflow_inputs).parameters) == ["workflow", "layers"]
    assert list(inspect.signature(render_workflow_preflight_markdown).parameters) == ["report"]


def test_preflight_internal_dependency_graph_is_one_way_and_acyclic():
    edges = _preflight_edges()
    assert edges == {
        "preflight": {"_preflight_model", "_preflight_render", "_preflight_report"},
        "_preflight_checks": {"_preflight_findings"},
        "_preflight_findings": set(),
        "_preflight_model": set(),
        "_preflight_render": {"_preflight_model"},
        "_preflight_report": {"_preflight_checks", "_preflight_findings", "_preflight_model"},
        "preflight_sarif": {"preflight"},
    }
    _assert_acyclic(edges)


def test_preflight_responsibilities_do_not_cross_import_boundaries():
    facade_imports = _relative_imports("preflight")
    assert facade_imports.isdisjoint({"contracts", "crs", "errors", "manifest"})

    findings_imports = _relative_imports("_preflight_findings")
    assert findings_imports == set()

    renderer_imports = _relative_imports("_preflight_render")
    assert renderer_imports.isdisjoint(
        {"_preflight_checks", "contracts", "crs", "geojson", "manifest", "operators", "workflow"}
    )

    sarif_imports = _relative_imports("preflight_sarif")
    assert sarif_imports.isdisjoint(
        {
            "_preflight_checks",
            "_preflight_findings",
            "_preflight_model",
            "_preflight_render",
            "_preflight_report",
        }
    )
