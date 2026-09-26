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
    dom_script = client.get("/workbench/dom.js")
    render_ui_script = client.get("/workbench/render_ui.js")
    render_review_script = client.get("/workbench/render_review.js")
    render_editor_script = client.get("/workbench/render_editor.js")
    render_preflight_script = client.get("/workbench/render_preflight.js")
    editor_script = client.get("/workbench/editor.js")
    assurance_script = client.get("/workbench/assurance.js")
    execution_script = client.get("/workbench/execution.js")
    render_execution_script = client.get("/workbench/render_execution.js")

    assert index.status_code == 200
    assert index.headers["content-type"].startswith("text/html")
    assert "Workflow assurance workbench" in index.text
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
    assert 'from "./assurance.js"' in script.text
    assert 'from "./editor.js"' in script.text
    assert 'from "./render.js"' in script.text

    assert api_script.status_code == 200
    assert "/api/v1/limits" in api_script.text
    assert "/api/v1/workflows/contract" in api_script.text
    assert "/api/v1/workflows/preflight" in api_script.text
    assert "/api/v1/workflows/execute" in api_script.text

    assert render_script.status_code == 200
    assert 'from "./render_ui.js"' in render_script.text
    assert 'from "./render_review.js"' in render_script.text
    assert 'from "./render_editor.js"' in render_script.text
    assert 'from "./render_preflight.js"' in render_script.text
    assert 'from "./render_execution.js"' in render_script.text

    assert dom_script.status_code == 200
    assert "textContent" in dom_script.text
    assert "innerHTML" not in dom_script.text

    assert render_ui_script.status_code == 200
    assert "initializeTabs" in render_ui_script.text

    assert render_review_script.status_code == 200
    assert "renderReports" in render_review_script.text

    assert render_editor_script.status_code == 200
    assert "operator.inputs" in render_editor_script.text
    assert "operator.parameters" in render_editor_script.text
    assert "input.contract" in render_editor_script.text

    assert render_preflight_script.status_code == 200
    assert "renderPreflightBindings" in render_preflight_script.text
    assert "renderPreflightReport" in render_preflight_script.text

    assert editor_script.status_code == 200
    assert "buildDraftStep" in editor_script.text
    assert "appendDraftStep" in editor_script.text

    assert assurance_script.status_code == 200
    assert "required_external_layers" in assurance_script.text
    assert "buildPreflightRequest" in assurance_script.text
    assert "assertPreflightEvidenceChain" in assurance_script.text

    assert execution_script.status_code == 200
    assert "buildExecutionRequest" in execution_script.text
    assert "assertExecutionEvidenceChain" in execution_script.text

    assert render_execution_script.status_code == 200
    assert "renderExecutionControls" in render_execution_script.text
    assert "renderExecutionResult" in render_execution_script.text


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


def test_workbench_uses_review_preflight_and_bounded_execution_endpoints() -> None:
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
        "/api/v1/workflows/execute",
    }
    for path in expected:
        assert path in script

    assert "starshine_geo" not in script
    assert "starshine_server" not in script


def test_assisted_editor_does_not_hard_code_catalog_operator_names() -> None:
    editor = (STATIC_ROOT / "editor.js").read_text(encoding="utf-8")
    catalog = starshine_geo.operator_catalog()

    for operator in catalog["operators"]:
        name = operator["name"]
        assert f'"{name}"' not in editor
        assert f"'{name}'" not in editor


def test_assisted_editor_keeps_core_defaults_and_validation_authoritative() -> None:
    editor = (STATIC_ROOT / "editor.js").read_text(encoding="utf-8")
    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert "parameter.default" not in editor
    assert "decoded.present" in editor
    assert "ENDPOINTS.validate" in app
    assert "A draft step was inserted. Run Review workflow for canonical validation." in app
    assert 'setReviewState(elements.reviewState, "Not reviewed")' in app
    assert "ENDPOINTS.execute" in app
    assert "state.preflight.valid !== true" in app
    assert "state.preflightRequest" in app


def test_inline_preflight_browser_layer_has_no_gis_or_upload_semantics() -> None:
    assurance = (STATIC_ROOT / "assurance.js").read_text(encoding="utf-8")
    index = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")

    assert "required_external_layers" in assurance
    assert "JSON.parse" in assurance
    assert "plan_digest" in assurance
    assert "contract_digest" in assurance

    lowered = assurance.lower()
    for forbidden in (
        "featurecollection",
        "geometry",
        "starshine:crs",
        "max_features",
        "max_total_features",
    ):
        assert forbidden not in lowered

    assert 'type="file"' not in index
    assert "multipart" not in lowered


def test_workbench_presentation_modules_keep_one_way_dependencies() -> None:
    facade = (STATIC_ROOT / "render.js").read_text(encoding="utf-8")
    domain_paths = [
        STATIC_ROOT / "render_ui.js",
        STATIC_ROOT / "render_review.js",
        STATIC_ROOT / "render_editor.js",
        STATIC_ROOT / "render_preflight.js",
        STATIC_ROOT / "render_assumptions.js",
        STATIC_ROOT / "render_execution.js",
    ]

    assert len(facade.splitlines()) < 40
    assert "document." not in facade
    assert "fetch(" not in facade

    for path in domain_paths:
        source = path.read_text(encoding="utf-8")
        for forbidden in (
            './api.js',
            './editor.js',
            './assurance.js',
            './execution.js',
            "fetch(",
            "/api/v1/",
        ):
            assert forbidden not in source

    dom = (STATIC_ROOT / "dom.js").read_text(encoding="utf-8")
    for forbidden in (
        './api.js',
        './editor.js',
        './assurance.js',
        './execution.js',
        "fetch(",
        "/api/v1/",
    ):
        assert forbidden not in dom


def test_crs_evidence_view_uses_canonical_reports_without_crs_engine() -> None:
    index = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    facade = (STATIC_ROOT / "render.js").read_text(encoding="utf-8")
    assumptions = (STATIC_ROOT / "render_assumptions.js").read_text(encoding="utf-8")
    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'id="crs-evidence-tab"' in index
    assert 'id="crs-evidence-content"' in index
    assert "renderCrsEvidence" in facade
    assert "resetCrsEvidence" in facade

    assert "input.source_kind" in assumptions
    assert "parameter.source" in assumptions
    assert "step.output_crs" in assumptions
    assert "equivalent_to_layer" in assumptions
    assert "workflow_digest" in assumptions
    assert "operator_catalog_digest" in assumptions
    assert "contract_digest" in assumptions
    assert "graph_digest" in assumptions
    assert "explanation_digest" in assumptions
    assert "preflight.preflight_digest" in assumptions

    for forbidden in (
        "proj4",
        "pyproj",
        "from_epsg",
        "to_epsg",
        "lookupCrs",
        "parseCrs",
        "reproject(",
        "/api/v1/",
        "fetch(",
        './api.js',
        './editor.js',
        './assurance.js',
    ):
        assert forbidden not in assumptions

    assert "Manifest workflow" in assumptions
    assert "Result layer" in assumptions
    assert "Core-generated manifest" in assumptions
    assert "renderCrsEvidence(elements.crsEvidence, state.reports, report, null)" in app
    assert "renderCrsEvidence(elements.crsEvidence, state.reports, state.preflight, execution)" in app
    assert "resetCrsEvidence(elements.crsEvidence" in app


def test_crs_evidence_preflight_digest_uses_existing_preflight_lifecycle() -> None:
    assumptions = (STATIC_ROOT / "render_assumptions.js").read_text(encoding="utf-8")
    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'preflight ? preflight.preflight_digest : "not available"' in assumptions
    assert 'Preflight evidence: ${preflight ? "current" : "not available"}' in assumptions
    assert "state.preflight = null" in app
    assert "renderCrsEvidence(elements.crsEvidence, state.reports, null)" in app


def test_browser_execution_helper_has_no_gis_or_dom_semantics() -> None:
    execution = (STATIC_ROOT / "execution.js").read_text(encoding="utf-8")

    assert "terminal_layers" in execution
    assert "preflight_digest" in execution
    assert "execution_policy" in execution
    assert "result" in execution
    assert "manifest" in execution

    lowered = execution.lower()
    for forbidden in (
        "featurecollection",
        "geometry",
        "starshine:crs",
        "document.",
        "window.",
        "fetch(",
        "/api/v1/",
        "proj4",
        "pyproj",
    ):
        assert forbidden not in lowered


def test_browser_execution_is_bound_to_current_passing_preflight() -> None:
    index = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    execution = (STATIC_ROOT / "execution.js").read_text(encoding="utf-8")

    assert 'id="execution-tab"' in index
    assert 'id="execution-output"' in index
    assert 'id="execution-button"' in index
    assert 'id="execution-result"' in index

    assert "state.preflightRequest = request" in app
    assert "buildExecutionRequest(state.preflightRequest, outputLayer)" in app
    assert "state.preflight.valid !== true" in app
    assert "resetExecution" in app
    assert "ENDPOINTS.execute" in app

    assert "execution.output_layer !== expectedOutputLayer" in execution
    assert "returnedPreflight.preflight_digest !== currentPreflight.preflight_digest" in execution
    assert "sameJson(execution.execution_policy, executionPolicy)" in execution
