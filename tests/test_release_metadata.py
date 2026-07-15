import re
from importlib.metadata import version
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised only on Python 3.10
    import tomli as tomllib

import starshine_geo
from scripts.check_release_readiness import check as check_release_readiness
from starshine_geo.cli import main
from starshine_geo.manifest import build_manifest

ROOT = Path(__file__).parents[1]


def _project_version() -> str:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(metadata["project"]["version"])


def test_release_version_is_consistent_across_public_metadata():
    project_version = _project_version()
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    citation_match = re.search(r"^version:\s*(\S+)\s*$", citation, flags=re.MULTILINE)
    assert citation_match is not None
    assert version("starshine-geo") == project_version
    assert starshine_geo.__version__ == project_version
    assert citation_match.group(1) == project_version
    assert f"## [{project_version}]" in changelog


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
    assert callable(starshine_geo.clip_features)
    assert callable(starshine_geo.dissolve_features)
    assert callable(starshine_geo.nearest_features)
    assert callable(starshine_geo.reproject_features)
    assert callable(starshine_geo.operator_catalog)
    assert callable(starshine_geo.plan_workflow)
    assert starshine_geo.WORKFLOW_PLAN_VERSION == 1
    assert "clip_features" in starshine_geo.__all__
    assert "dissolve_features" in starshine_geo.__all__
    assert "nearest_features" in starshine_geo.__all__
    assert "reproject_features" in starshine_geo.__all__
    assert "operator_catalog" in starshine_geo.__all__
    assert "plan_workflow" in starshine_geo.__all__
    assert "WORKFLOW_PLAN_VERSION" in starshine_geo.__all__


def test_release_readiness_check_matches_current_public_metadata():
    summary = check_release_readiness(ROOT)
    assert summary["version"] == _project_version()
    assert summary["release_date"] == "2026-07-14"
    assert summary["release_notes"] == f"docs/releases/{_project_version()}.md"
