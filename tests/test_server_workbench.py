from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

import starshine_geo
from starshine_server import create_app

ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "src" / "starshine_server" / "static"


def _client() -> TestClient:
    return TestClient(create_app())


def test_workbench_assets_are_served_from_the_server_package() -> None:
    client = _client()

    index = client.get("/workbench/")
    stylesheet = client.get("/workbench/styles.css")
    script = client.get("/workbench/app.js")
    api_script = client.get("/workbench/api.js")
    render_script = client.get("/workbench/render.js")
    composer_script = client.get("/workbench/composer.js")
    assurance_script = client.get("/workbench/assurance.js")

    assert index.status_code == 200
    assert index.headers["content-type"].startswith("text/html")
    assert "Workflow review workbench" in index.text
    assert 'href="./styles.css"' in index.text
    assert 'src="./app.js"' in index.text
    assert "Content-Security-Policy" in index.text
    assert "connect-src 'self'" in index.text

    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert ".workbench-grid" in stylesheet.text

    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert 'from "./api.js"' in script.text
    assert 'from "./render.js"' in script.text
    assert 'from "./composer.js"' in script.text

    assert api_script.status_code == 200
    assert "/api/v1/workflows/contract" in api_script.text

    assert render_script.status_code == 200
    assert "textContent" in render_script.text

    assert composer_script.status_code == 200
    assert "buildStepDraft" in composer_script.text
    assert "parameter.default" in composer_script.text

    assert assurance_script.status_code == 200
    assert "assertPreflightMatchesReview" in assurance_script.text
    assert "parseNamedLayers" in assurance_script.text


def test_workbench_has_no_external_browser_runtime_or_dynamic_html_sink() -> None:
    index = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    stylesheet = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")
    scripts = [
        path.read_text(encoding="utf-8")
        for path in sorted(STATIC_ROOT.glob("*.js"))
    ]
    script = "\n".join(scripts)
    combined = f"{index}\n{stylesheet}\n{script}"

    for external_marker in ("http://", "https://", "//cdn."):
        assert external_marker not in combined

    for forbidden in (
        "innerHTML",
        "outerHTML",
        "document.write",
        "eval(",
        "new Function",
        "localStorage",
        "sessionStorage",
    ):
        assert forbidden not in script


def test_workbench_uses_review_and_preflight_endpoints_without_execution() -> None:
    script = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(STATIC_ROOT.glob("*.js"))
    )

    expected = {
        "/healthz",
        "/api/v1/operators",
        "/api/v1/limits",
        "/api/v1/workflows/validate",
        "/api/v1/workflows/plan",
        "/api/v1/workflows/contract",
        "/api/v1/workflows/graph",
        "/api/v1/workflows/explain",
        "/api/v1/workflows/preflight",
    }
    for path in expected:
        assert path in script

    assert "/api/v1/workflows/execute" not in script
    assert "starshine_geo" not in script
    assert "starshine_server" not in script


def test_step_composer_has_no_operator_specific_branches() -> None:
    composer = (STATIC_ROOT / "composer.js").read_text(encoding="utf-8")
    catalog = starshine_geo.operator_catalog()

    for operator in catalog["operators"]:
        name = operator["name"]
        assert f'case "{name}"' not in composer
        assert f"case '{name}'" not in composer
        assert f'if (operator.name === "{name}")' not in composer
        assert f"if (operator.name === '{name}')" not in composer

    assert "parameter.validator" not in composer
    assert "source_crs" not in composer
    assert "work_crs" not in composer
    assert "EPSG:" not in composer


def test_step_composer_keeps_canonical_validation_as_the_authority() -> None:
    composer = (STATIC_ROOT / "composer.js").read_text(encoding="utf-8")
    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert "JSON.parse(raw)" in composer
    assert "workflow.steps.push(step)" in app
    assert "ENDPOINTS.validate" in app
    assert "Review workflow" in (STATIC_ROOT / "index.html").read_text(encoding="utf-8")


def test_preflight_ui_is_gated_by_review_freshness() -> None:
    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert "reviewFresh: false" in app
    assert "elements.preflightButton.disabled = true" in app
    assert "elements.workflow.addEventListener(\"input\", onReviewedInputChanged)" in app
    assert "elements.layerNames.addEventListener(\"input\", onReviewedInputChanged)" in app
    assert "elements.preflightLayers.addEventListener(\"input\", onPreflightDataChanged)" in app
    assert "assertPreflightMatchesReview(state.reports, report)" in app


def test_assurance_module_does_not_reimplement_geojson_or_crs_validation() -> None:
    assurance = (STATIC_ROOT / "assurance.js").read_text(encoding="utf-8")

    assert "workflow_digest" in assurance
    assert "plan_digest" in assurance
    assert "contract_digest" in assurance
    assert "geometry" not in assurance
    assert "FeatureCollection" not in assurance
    assert "EPSG:" not in assurance
    assert "starshine:crs" not in assurance


def test_assumptions_view_uses_canonical_reports_without_crs_engine() -> None:
    render = (STATIC_ROOT / "render.js").read_text(encoding="utf-8")
    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    index = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")

    assert 'id="assumptions-tab"' in index
    assert 'id="assumptions-content"' in index
    assert "renderAssumptions" in render
    assert "use.crs" in render
    assert "step.output_crs" in render
    assert "reports.plan.produced_layers" in render
    assert "reports.plan.terminal_layers" in render
    assert "operator_catalog_digest" in render
    assert "preflight.preflight_digest" in render

    for forbidden in (
        "proj4",
        "pyproj",
        "reproject",
        "from_epsg",
        "to_epsg",
        "lookupCrs",
        "parseCrs",
    ):
        assert forbidden not in render

    assert "reviewFresh" in app
    assert "state.preflight" in app
    assert "refreshAssumptions()" in app


def test_assumptions_view_does_not_claim_execution_provenance() -> None:
    render = (STATIC_ROOT / "render.js").read_text(encoding="utf-8")

    assert "not execution provenance" in render
    assert "Result and manifest evidence only exist after canonical execution" in render
    assert "execution_manifest" not in render
