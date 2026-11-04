from __future__ import annotations

import base64
import json
import re
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


def test_workbench_uses_only_review_and_inline_preflight_endpoints() -> None:
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
    paths = set(re.findall(r'[\"\'](/(?:api/[^\"\']+|healthz))[\"\']', script))
    assert paths == expected

    assert "/api/v1/workflows/execute" not in script
    assert "starshine_geo" not in script
    assert "starshine_server" not in script
    for forbidden in ("FormData", "FileReader", "indexedDB", "serviceWorker"):
        assert forbidden not in script
    index = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    assert 'type="file"' not in index


def test_inline_preflight_assets_are_served_with_the_workbench() -> None:
    client = _client()
    for name in ("assurance.js", "render_preflight.js"):
        response = client.get(f"/workbench/{name}")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
    script = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    assert 'from "./assurance.js"' in script
    assert 'from "./render_preflight.js"' in script


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


def _browser_review_body(raw: str, layer_names: list[str]) -> str:
    """Run the packaged transport, not a Python approximation of its envelope."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to exercise the shipped Review transport")
    source = base64.b64encode((STATIC_ROOT / "api.js").read_bytes()).decode("ascii")
    script = """
      import { readFileSync } from 'node:fs';
      const { source, raw, layerNames } = JSON.parse(readFileSync(0, 'utf8'));
      const { requestJson } = await import(`data:text/javascript;base64,${source}`);
      globalThis.fetch = async (_path, init) => {
        process.stdout.write(init.body);
        return { ok: true, text: async () => '{"valid":true}' };
      };
      await requestJson('/api/v1/workflows/validate', {
        method: 'POST', workflowText: raw, layerNames,
      });
    """
    return subprocess.run(
        [node, "--input-type=module", "-e", script],
        input=json.dumps({"source": source, "raw": raw, "layerNames": layer_names}),
        text=True, capture_output=True, check=True,
    ).stdout


@pytest.mark.parametrize("number", ["8.0", "-0.0", "9007199254740993"])
def test_review_transport_preserves_core_parameters_and_evidence(number: str) -> None:
    names = ['points"\\', "polygons"]
    raw = (
        '{"version":1.0,"steps":[{"operation":"join_points_to_polygons",'
        '"inputs":{"points":' + json.dumps(names[0]) + ',"polygons":"polygons"},'
        '"parameters":{"polygon_id_field":"id","unmatched_value":' + number + '},'
        '"output":"joined"}]}'
    )
    body = _browser_review_body(raw, names)
    assert body.startswith('{"workflow":' + raw + ',"layer_names":')
    workflow = json.loads(raw)
    client = _client()
    for endpoint, build in (
        ("plan", starshine_geo.plan_workflow),
        ("contract", starshine_geo.build_workflow_contract),
        ("graph", starshine_geo.build_workflow_graph),
        ("explain", starshine_geo.explain_workflow),
    ):
        response = client.post(
            f"/api/v1/workflows/{endpoint}", content=body,
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json() == build(workflow, names)
        assert response.json()["workflow_digest"] == starshine_geo.plan_workflow(
            workflow, names,
        )["workflow_digest"]


@pytest.mark.parametrize(
    "raw,status,code",
    [
        (
            ('{"version":1,"steps":[{"operation":"buffer","inputs":{"input":"source"},'
             '"parameters":{"distance":1,"segments":8.0,"source_crs":"EPSG:4326",'
             '"work_crs":"EPSG:3857"},"output":"result"}]}'),
            422, "invalid_parameter",
        ),
        ('{"version":1,"steps":[],"overflow":1e400}', 400, "invalid_json"),
        ('{"nested":' + "[" * 66 + "0" + "]" * 66 + "}", 413, "json_nesting_too_deep"),
        (" " * (2 * 1024 * 1024) + '{"version":1,"steps":[]}', 413,
         "request_body_too_large"),
    ],
)
def test_review_transport_preserves_server_rejections(raw: str, status: int, code: str) -> None:
    body = _browser_review_body(raw, ["source"])
    client = _client()
    for endpoint in ("validate", "plan", "contract", "graph", "explain"):
        response = client.post(
            f"/api/v1/workflows/{endpoint}", content=body,
            headers={"content-type": "application/json"},
        )
        assert response.status_code == status
        payload = response.json()
        actual_code = payload.get("diagnostic", {}).get("code", payload.get("code", payload["error"]))
        assert actual_code == code


def _nearest_workflow_text(number: str = "1.0", source_name: str = "sources") -> str:
    return (
        ' {"version":1.0,"steps":[{"operation":"nearest","inputs":{"source":'
        + json.dumps(source_name, ensure_ascii=False)
        + ',"candidates":"candidates"},"parameters":{"candidate_id_field":"id",'
        '"max_distance":' + number + '},"output":"matched"}]}\n'
    )

def _collection_text(ids: tuple[str, ...] = ('"source"',)) -> str:
    features = [
        '{"type":"Feature","properties":{"id":' + value + '},'
        '"geometry":{"type":"Point","coordinates":[1.0,-0.0]}}'
        for value in ids
    ]
    return (
        ' \n{"type":"FeatureCollection","starshine:crs":"EPSG:3857","features":['
        + ",".join(features) + ']}\t'
    )


def _canonical_review_reports(raw: str, names: list[str]) -> dict:
    workflow = json.loads(raw)
    return {
        "plan": starshine_geo.plan_workflow(workflow, names),
        "contract": starshine_geo.build_workflow_contract(workflow, names),
    }


def _browser_preflight_body(raw: str, layer_texts: list[tuple[str, str]], reports: dict) -> str:
    """Exercise both shipped helper and HTTP transport, preserving their exact bytes."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to exercise the shipped inline Preflight transport")
    sources = {
        name: base64.b64encode((STATIC_ROOT / name).read_bytes()).decode("ascii")
        for name in ("api.js", "assurance.js")
    }
    script = """
      import assert from 'node:assert/strict';
      import { readFileSync } from 'node:fs';
      const { sources, raw, layerTexts, reports } = JSON.parse(readFileSync(0, 'utf8'));
      const { ENDPOINTS, requestJson } =
        await import(`data:text/javascript;base64,${sources['api.js']}`);
      const { buildPreflightRequest } =
        await import(`data:text/javascript;base64,${sources['assurance.js']}`);
      globalThis.fetch = async (path, init) => {
        assert.equal(path, '/api/v1/workflows/preflight');
        assert.equal(init.method, 'POST');
        assert.equal(init.headers['content-type'], 'application/json');
        process.stdout.write(init.body);
        return { ok: true, text: async () => '{"valid":true}' };
      };
      await requestJson(ENDPOINTS.preflight,
        buildPreflightRequest(raw, reports, new Map(layerTexts)));
    """
    return subprocess.run(
        [node, "--input-type=module", "-e", script],
        input=json.dumps({
            "sources": sources, "raw": raw, "layerTexts": layer_texts, "reports": reports,
        }),
        text=True, capture_output=True, check=True,
    ).stdout


def _post_preflight_body(body: str):
    return _client().post(
        "/api/v1/workflows/preflight", content=body,
        headers={"content-type": "application/json"},
    )


@pytest.mark.parametrize("number", ["1.0", "-0.0", "9007199254740993"])
def test_preflight_transport_keeps_typed_identifiers_and_canonical_nearest_pass(number: str) -> None:
    raw = _nearest_workflow_text(number)
    reports = _canonical_review_reports(raw, ["sources", "candidates"])
    layer_texts = [
        ("sources", _collection_text()),
        ("candidates", _collection_text((
            "1", "1.0", "-0.0", "0.0", "9007199254740992", "9007199254740993",
        ))),
    ]
    body = _browser_preflight_body(raw, layer_texts, reports)
    texts = dict(layer_texts)
    expected_entries = ",".join(
        json.dumps(name) + ":" + texts[name]
        for name in reports["plan"]["required_external_layers"]
    )
    assert body == '{"workflow":' + raw + ',"layers":{' + expected_entries + "}}"
    assert set(json.loads(body)) == {"workflow", "layers"}
    layers = {name: json.loads(value) for name, value in layer_texts}
    response = _post_preflight_body(body)
    assert response.status_code == 200
    report = response.json()
    assert report == starshine_geo.preflight_workflow_inputs(json.loads(raw), layers)
    assert report["valid"] is True
    assert report["error_count"] == 0
    assert report["checked_layer_count"] == 2
    assert report["workflow_digest"] == reports["plan"]["workflow_digest"]
    assert report["plan_digest"] == reports["plan"]["plan_digest"]
    assert report["contract_digest"] == reports["contract"]["contract_digest"]
    for layer in report["layers"]:
        assert layer["collection_digest"] == starshine_geo.digest_json(layers[layer["name"]])


@pytest.mark.parametrize("name", ["__proto__", "constructor", 'quote"', "back\\slash", "河流😀"])
def test_preflight_transport_keeps_unusual_layer_names_as_ordinary_json_keys(name: str) -> None:
    raw = _nearest_workflow_text(source_name=name)
    reports = _canonical_review_reports(raw, [name, "candidates"])
    layer_texts = [(name, _collection_text()), ("candidates", _collection_text(("1",)))]
    body = _browser_preflight_body(raw, layer_texts, reports)
    assert set(json.loads(body)["layers"]) == {name, "candidates"}
    assert json.dumps(name, ensure_ascii=False) + ":" in body
    response = _post_preflight_body(body)
    assert response.status_code == 200
    assert response.json() == starshine_geo.preflight_workflow_inputs(
        json.loads(raw), {key: json.loads(value) for key, value in layer_texts},
    )
    assert response.json()["valid"] is True


@pytest.mark.parametrize("location", ["workflow", "layer"])
@pytest.mark.parametrize(
    "value,status,code",
    [
        ("1e400", 400, "invalid_json"),
        ("[" * 66 + "0" + "]" * 66, 413, "json_nesting_too_deep"),
        (" " * (2 * 1024 * 1024) + "0", 413, "request_body_too_large"),
    ],
    ids=["overflow", "depth", "body-size"],
)
def test_preflight_transport_preserves_server_boundaries(
    location: str, value: str, status: int, code: str,
) -> None:
    raw = _nearest_workflow_text()
    reports = _canonical_review_reports(raw, ["sources", "candidates"])
    layer_texts = [("sources", _collection_text()), ("candidates", _collection_text(("1",)))]
    if location == "workflow":
        raw = raw.rstrip()[:-1] + ',"transport_probe":' + value + "}"
    else:
        layer_texts[0] = ("sources", '{"transport_probe":' + value + "}")
    body = _browser_preflight_body(raw, layer_texts, reports)
    assert value in body
    response = _post_preflight_body(body)
    assert response.status_code == status
    payload = response.json()
    assert payload.get("code", payload["error"]) == code


@pytest.mark.parametrize("value", ["null", "[]", "1.0", "true", '"not GeoJSON"'])
def test_preflight_layer_root_shape_is_rejected_by_server_not_browser(value: str) -> None:
    raw = _nearest_workflow_text()
    reports = _canonical_review_reports(raw, ["sources", "candidates"])
    body = _browser_preflight_body(
        raw, [("sources", value), ("candidates", _collection_text(("1",)))], reports,
    )
    assert '"sources":' + value in body
    response = _post_preflight_body(body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "layers", "sources"]
    assert response.json()["detail"][0]["type"] == "dict_type"


@pytest.mark.parametrize(
    "value",
    [
        "{}",
        '{"type":"FeatureCollection","features":"not-a-list"}',
        '{"type":"FeatureCollection","features":[],"starshine:crs":"not-a-crs"}',
        '{"type":"FeatureCollection","features":[]}',
    ],
)
def test_preflight_invalid_geojson_reaches_canonical_core_fail_report(value: str) -> None:
    raw = _nearest_workflow_text()
    reports = _canonical_review_reports(raw, ["sources", "candidates"])
    layer_texts = [("sources", value), ("candidates", _collection_text(("1",)))]
    body = _browser_preflight_body(raw, layer_texts, reports)
    response = _post_preflight_body(body)
    assert response.status_code == 200
    assert response.json() == starshine_geo.preflight_workflow_inputs(
        json.loads(raw), {name: json.loads(text) for name, text in layer_texts},
    )
    assert response.json()["valid"] is False
    assert response.json()["error_count"] > 0


@pytest.mark.parametrize("blank", ["", " \n\t"])
def test_preflight_blank_draft_is_omitted_and_missing_layer_is_server_owned(blank: str) -> None:
    raw = _nearest_workflow_text()
    reports = _canonical_review_reports(raw, ["sources", "candidates"])
    body = _browser_preflight_body(raw, [
        ("sources", blank), ("candidates", _collection_text(("1",))),
        ("not-required", "not JSON and must not be submitted"),
    ], reports)
    assert set(json.loads(body)["layers"]) == {"candidates"}
    response = _post_preflight_body(body)
    assert response.status_code == 422
    assert response.json()["diagnostic"]["code"] == "unknown_input_layer"
    assert response.json()["diagnostic"]["path"] == "steps[0].inputs.source"
