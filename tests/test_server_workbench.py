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
    editor_script = client.get("/workbench/editor.js")
    assurance_script = client.get("/workbench/assurance.js")

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

    assert render_script.status_code == 200
    assert "textContent" in render_script.text
    assert "operator.inputs" in render_script.text
    assert "operator.parameters" in render_script.text
    assert "input.contract" in render_script.text

    assert editor_script.status_code == 200
    assert "buildDraftStep" in editor_script.text
    assert "appendDraftStep" in editor_script.text

    assert assurance_script.status_code == 200
    assert "required_external_layers" in assurance_script.text
    assert "buildPreflightRequest" in assurance_script.text
    assert "assertPreflightEvidenceChain" in assurance_script.text


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


def test_workbench_uses_review_and_preflight_endpoints_but_never_execution() -> None:
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
    assert "/api/v1/workflows/execute" not in app


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
