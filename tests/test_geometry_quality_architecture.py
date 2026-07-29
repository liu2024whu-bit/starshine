from __future__ import annotations

import ast
import inspect
from pathlib import Path

from starshine_geo import assess_geometry_quality, render_geometry_quality_markdown

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "starshine_geo"
QUALITY_MODULES = {
    "geometry_quality",
    "_geometry_quality_coordinates",
    "_geometry_quality_findings",
    "_geometry_quality_model",
    "_geometry_quality_render",
    "_geometry_quality_report",
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


def _quality_edges() -> dict[str, set[str]]:
    return {
        module: _relative_imports(module) & QUALITY_MODULES for module in QUALITY_MODULES
    }


def _assert_acyclic(edges: dict[str, set[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module: str) -> None:
        if module in visiting:
            raise AssertionError(f"circular geometry-quality dependency detected at {module}")
        if module in visited:
            return
        visiting.add(module)
        for dependency in edges[module]:
            visit(dependency)
        visiting.remove(module)
        visited.add(module)

    for module in edges:
        visit(module)


def test_geometry_quality_facade_is_small_and_preserves_public_callable_identity():
    facade_path = PACKAGE_ROOT / "geometry_quality.py"
    assert len(facade_path.read_text(encoding="utf-8").splitlines()) <= 60
    assert assess_geometry_quality.__module__ == "starshine_geo.geometry_quality"
    assert render_geometry_quality_markdown.__module__ == "starshine_geo.geometry_quality"
    assert list(inspect.signature(assess_geometry_quality).parameters) == ["collection"]
    assert list(inspect.signature(render_geometry_quality_markdown).parameters) == ["report"]


def test_geometry_quality_dependency_graph_is_one_way_and_acyclic():
    edges = _quality_edges()
    assert edges == {
        "geometry_quality": {
            "_geometry_quality_model",
            "_geometry_quality_render",
            "_geometry_quality_report",
        },
        "_geometry_quality_coordinates": set(),
        "_geometry_quality_findings": set(),
        "_geometry_quality_model": set(),
        "_geometry_quality_render": {"_geometry_quality_model"},
        "_geometry_quality_report": {
            "_geometry_quality_coordinates",
            "_geometry_quality_findings",
            "_geometry_quality_model",
        },
    }
    _assert_acyclic(edges)


def test_geometry_quality_responsibilities_do_not_cross_import_boundaries():
    for module in QUALITY_MODULES - {"geometry_quality"}:
        assert "geometry_quality" not in _relative_imports(module)

    renderer_imports = _relative_imports("_geometry_quality_render")
    assert renderer_imports.isdisjoint(
        {
            "_geometry_quality_coordinates",
            "_geometry_quality_findings",
            "_geometry_quality_report",
            "contracts",
            "crs",
            "geojson",
            "manifest",
            "operators",
            "preflight",
            "workflow",
        }
    )

    report_imports = _relative_imports("_geometry_quality_report")
    assert report_imports.isdisjoint(
        {
            "_geometry_quality_render",
            "contracts",
            "operators",
            "preflight",
            "preflight_sarif",
            "workflow",
        }
    )
