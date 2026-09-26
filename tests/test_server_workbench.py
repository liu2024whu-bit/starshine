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
    authoring_script = client.get("/workbench/authoring.js")

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

    assert api_script.status_code == 200
    assert "/api/v1/workflows/contract" in api_script.text

    assert render_script.status_code == 200
    assert "textContent" in render_script.text

    assert authoring_script.status_code == 200
    assert "buildCandidateStep" in authoring_script.text
    assert "JSON.parse" in authoring_script.text


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


def test_workbench_first_slice_uses_review_endpoints_only() -> None:
    script = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(STATIC_ROOT.glob("*.js"))
    )

    expected = {
        "/healthz",
        "/api/v1/operators",
        "/api/v1/workflows/validate",
        "/api/v1/workflows/plan",
        "/api/v1/workflows/contract",
        "/api/v1/workflows/graph",
        "/api/v1/workflows/explain",
    }
    for path in expected:
        assert path in script

    assert "/api/v1/workflows/preflight" not in script
    assert "/api/v1/workflows/execute" not in script
    assert "starshine_geo" not in script
    assert "starshine_server" not in script


def test_workbench_authoring_stays_catalog_driven_and_schema_display_only() -> None:
    source = (STATIC_ROOT / "authoring.js").read_text(encoding="utf-8")

    catalog = starshine_geo.operator_catalog()
    operator_names = [item["name"] for item in catalog["operators"]]
    for name in operator_names:
        assert f'"{name}"' not in source
        assert f"'{name}'" not in source

    assert "parameter.schema" in source
    assert "JSON.stringify(parameter.schema)" in source
    assert "JSON.parse(text)" in source
    assert "Default from catalog:" in source
    assert 'control.value = ""' in source

    for forbidden_semantics in (
        "exclusiveMinimum",
        "minimum",
        "maximum",
        "pattern",
        "anyOf",
        "EPSG:",
        "pyproj",
        "proj4",
    ):
        assert forbidden_semantics not in source


def test_workbench_step_builder_does_not_expand_the_network_boundary() -> None:
    source = (STATIC_ROOT / "authoring.js").read_text(encoding="utf-8")

    assert "fetch(" not in source
    assert "XMLHttpRequest" not in source
    assert "/api/" not in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
