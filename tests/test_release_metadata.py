import re
from importlib.metadata import version
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised only on Python 3.10
    import tomli as tomllib

import starshine_geo
from scripts.check_release_artifacts import _package_python_suffixes
from scripts.check_release_readiness import check as check_release_readiness
from starshine_geo.cli import main
from starshine_geo.manifest import build_manifest

ROOT = Path(__file__).parents[1]


def _project_version() -> str:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(metadata["project"]["version"])


def test_release_artifact_package_surface_is_derived_from_source_tree(tmp_path):
    source_root = tmp_path / "src" / "starshine_geo"
    nested = source_root / "nested"
    nested.mkdir(parents=True)
    (source_root / "__init__.py").write_text("", encoding="utf-8")
    (source_root / "workflow.py").write_text("", encoding="utf-8")
    (nested / "helper.py").write_text("", encoding="utf-8")
    (source_root / "README.txt").write_text("not a module", encoding="utf-8")

    assert _package_python_suffixes(source_root) == (
        "starshine_geo/__init__.py",
        "starshine_geo/nested/helper.py",
        "starshine_geo/workflow.py",
    )


def test_release_artifact_package_surface_covers_current_core_modules():
    suffixes = set(_package_python_suffixes(ROOT / "src" / "starshine_geo"))

    assert {
        "starshine_geo/geojson.py",
        "starshine_geo/workflow.py",
        "starshine_geo/manifest.py",
        "starshine_geo/geopackage.py",
        "starshine_geo/io.py",
    } <= suffixes


def test_development_version_is_distinct_from_latest_release_metadata():
    project_version = _project_version()
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    citation_match = re.search(r"^version:\s*(\S+)\s*$", citation, flags=re.MULTILINE)
    assert citation_match is not None
    assert version("starshine-geo") == project_version
    assert starshine_geo.__version__ == project_version
    assert project_version == "0.7.0.dev0"
    assert citation_match.group(1) == "0.4.0"
    assert project_version != citation_match.group(1)
    assert "## [Unreleased]" in changelog
    assert "## [0.4.0] - 2026-07-29" in changelog


def test_manifest_uses_installed_package_version_by_default():
    collection = {"type": "FeatureCollection", "features": []}
    manifest = build_manifest(
        {"version": 1, "steps": []},
        {},
        output_layer_name="empty",
        output_layer=collection,
    )
    assert manifest["starshine_version"] == _project_version()


def test_cli_reports_installed_version(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"starshine {_project_version()}"


def test_top_level_api_exports_public_operator_surfaces():
    assert callable(starshine_geo.assess_geometry_quality)
    assert callable(starshine_geo.build_workflow_graph)
    assert callable(starshine_geo.build_workflow_preflight_sarif)
    assert callable(starshine_geo.build_workflow_contract)
    assert callable(starshine_geo.clip_features)
    assert callable(starshine_geo.calculate_geometry_metrics)
    assert callable(starshine_geo.difference_features)
    assert callable(starshine_geo.dissolve_features)
    assert callable(starshine_geo.explain_workflow)
    assert callable(starshine_geo.intersect_features)
    assert callable(starshine_geo.join_points_to_polygons)
    assert callable(starshine_geo.nearest_features)
    assert callable(starshine_geo.reproject_features)
    assert callable(starshine_geo.operator_catalog)
    assert callable(starshine_geo.plan_workflow)
    assert callable(starshine_geo.preflight_workflow_inputs)
    assert callable(starshine_geo.render_geometry_quality_markdown)
    assert callable(starshine_geo.render_workflow_contract_markdown)
    assert callable(starshine_geo.render_workflow_explanation_markdown)
    assert callable(starshine_geo.render_workflow_mermaid)
    assert callable(starshine_geo.render_workflow_preflight_markdown)
    assert starshine_geo.GEOMETRY_QUALITY_REPORT_VERSION == 1
    assert starshine_geo.WORKFLOW_CONTRACT_VERSION == 1
    assert starshine_geo.WORKFLOW_EXPLANATION_VERSION == 1
    assert starshine_geo.WORKFLOW_GRAPH_VERSION == 1
    assert starshine_geo.WORKFLOW_PLAN_VERSION == 1
    assert starshine_geo.WORKFLOW_PREFLIGHT_VERSION == 1
    assert starshine_geo.SARIF_VERSION == "2.1.0"
    assert starshine_geo.SARIF_SCHEMA_URI.endswith("sarif-2.1.0.json")
    assert "assess_geometry_quality" in starshine_geo.__all__
    assert "build_workflow_graph" in starshine_geo.__all__
    assert "build_workflow_preflight_sarif" in starshine_geo.__all__
    assert "build_workflow_contract" in starshine_geo.__all__
    assert "clip_features" in starshine_geo.__all__
    assert "calculate_geometry_metrics" in starshine_geo.__all__
    assert "difference_features" in starshine_geo.__all__
    assert "dissolve_features" in starshine_geo.__all__
    assert "explain_workflow" in starshine_geo.__all__
    assert "intersect_features" in starshine_geo.__all__
    assert "join_points_to_polygons" in starshine_geo.__all__
    assert "nearest_features" in starshine_geo.__all__
    assert "reproject_features" in starshine_geo.__all__
    assert "operator_catalog" in starshine_geo.__all__
    assert "plan_workflow" in starshine_geo.__all__
    assert "preflight_workflow_inputs" in starshine_geo.__all__
    assert "render_geometry_quality_markdown" in starshine_geo.__all__
    assert "render_workflow_contract_markdown" in starshine_geo.__all__
    assert "render_workflow_explanation_markdown" in starshine_geo.__all__
    assert "render_workflow_mermaid" in starshine_geo.__all__
    assert "render_workflow_preflight_markdown" in starshine_geo.__all__
    assert "GEOMETRY_QUALITY_REPORT_VERSION" in starshine_geo.__all__
    assert "WORKFLOW_CONTRACT_VERSION" in starshine_geo.__all__
    assert "WORKFLOW_EXPLANATION_VERSION" in starshine_geo.__all__
    assert "WORKFLOW_GRAPH_VERSION" in starshine_geo.__all__
    assert "WORKFLOW_PLAN_VERSION" in starshine_geo.__all__
    assert "WORKFLOW_PREFLIGHT_VERSION" in starshine_geo.__all__
    assert "SARIF_VERSION" in starshine_geo.__all__
    assert "SARIF_SCHEMA_URI" in starshine_geo.__all__


def test_release_readiness_check_matches_development_and_stable_metadata():
    summary = check_release_readiness(ROOT)
    assert summary == {
        "version": "0.7.0.dev0",
        "mode": "development",
        "release_version": "0.4.0",
        "release_date": "2026-07-29",
        "release_notes": "docs/releases/0.4.0.md",
    }

    with pytest.raises(RuntimeError, match="development snapshot"):
        check_release_readiness(ROOT, require_release=True)


def test_release_readiness_stable_mode_remains_executable(tmp_path):
    (tmp_path / "docs" / "releases").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "1.2.3"\n',
        encoding="utf-8",
    )
    (tmp_path / "CITATION.cff").write_text(
        "version: 1.2.3\ndate-released: 2026-09-19\n",
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [1.2.3] - 2026-09-19\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "releases" / "1.2.3.md").write_text(
        "# Starshine Geo 1.2.3\n\nRelease evidence.\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "[![Status](https://img.shields.io/badge/"
        "status-1.2.3%20research%20preview-orange.svg)](ROADMAP.md)\n\n"
        "[1.2.3 release notes](docs/releases/1.2.3.md)\n\n"
        "Starshine Geo 1.2.3 is an alpha-quality research preview.\n",
        encoding="utf-8",
    )

    summary = check_release_readiness(tmp_path, require_release=True)
    assert summary["mode"] == "release"
    assert summary["version"] == "1.2.3"
    assert summary["release_version"] == "1.2.3"
