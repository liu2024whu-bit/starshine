from __future__ import annotations

import base64
import json
import shutil
import subprocess
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

def test_workbench_invalidates_review_responses_after_input_edits() -> None:
    script = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert "reviewRequestId: 0" in script
    assert "function invalidateReview()" in script
    assert "renderReports(elements, null);" in script
    assert "elements.reviewButton.disabled = false;" in script
    assert "elements.workflow.addEventListener(\"input\", invalidateReview)" in script
    assert "elements.layerNames.addEventListener(\"input\", invalidateReview)" in script
    assert "if (requestId !== state.reviewRequestId) return;" in script
    assert "if (requestId === state.reviewRequestId)" in script



def test_assisted_editor_assets_and_catalog_independence() -> None:
    client = _client()
    for name in ("editor.js", "render_editor.js"):
        response = client.get(f"/workbench/{name}")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
    editor = (STATIC_ROOT / "editor.js").read_text(encoding="utf-8")
    for operator in starshine_geo.operator_catalog()["operators"]:
        assert json.dumps(operator["name"]) not in editor
    assert "parameter.default" not in editor


@pytest.mark.parametrize("distance,valid", [("2", True), ('"wrong type"', False), ("", False)])
def test_catalog_draft_agrees_with_canonical_core_and_http(distance, valid) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to execute the shipped draft transformer")
    source = base64.b64encode((STATIC_ROOT / "editor.js").read_bytes()).decode("ascii")
    catalog = starshine_geo.operator_catalog()
    script = """
      import { readFileSync } from 'node:fs';
      const { source, catalog, distance } = JSON.parse(readFileSync(0, 'utf8'));
      const { buildDraftStep, appendDraftStep, findCatalogOperator } =
        await import(`data:text/javascript;base64,${source}`);
      const step = buildDraftStep(findCatalogOperator(catalog, 'buffer'), { input: 'source' },
        { distance, source_crs: '\"EPSG:4326\"', work_crs: '\"EPSG:3857\"' }, 'result');
      console.log(JSON.stringify(appendDraftStep({version: 1, steps: []}, step)));
    """
    completed = subprocess.run(
        [node, "--input-type=module", "-e", script],
        input=json.dumps({"source": source, "catalog": catalog, "distance": distance}),
        text=True, capture_output=True, check=True,
    )
    workflow = json.loads(completed.stdout)
    assert set(workflow["steps"][0]["parameters"]) <= {
        "distance", "source_crs", "work_crs",
    }
    request = {"workflow": workflow, "layer_names": ["source"]}
    response = _client().post("/api/v1/workflows/validate", json=request)
    if valid:
        starshine_geo.validate_workflow(workflow, ["source"])
        assert response.status_code == 200
        assert response.json()["valid"] is True
        for endpoint, build in (
            ("plan", starshine_geo.plan_workflow),
            ("contract", starshine_geo.build_workflow_contract),
            ("graph", starshine_geo.build_workflow_graph),
            ("explain", starshine_geo.explain_workflow),
        ):
            report = _client().post(f"/api/v1/workflows/{endpoint}", json=request)
            assert report.status_code == 200
            assert report.json() == build(workflow, ["source"])
    else:
        with pytest.raises(starshine_geo.ValidationError):
            starshine_geo.validate_workflow(workflow, ["source"])
        assert response.status_code == 422
