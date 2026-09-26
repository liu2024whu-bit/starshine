from __future__ import annotations

from fastapi.testclient import TestClient

import starshine_geo
from starshine_server import create_app


def _point_layer() -> dict:
    return {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:4326",
        "features": [
            {
                "type": "Feature",
                "properties": {"id": 1},
                "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
            }
        ],
    }


def _mask_layer() -> dict:
    return {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:4326",
        "features": [
            {
                "type": "Feature",
                "properties": {"id": "mask"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-1.0, -1.0],
                        [1.0, -1.0],
                        [1.0, 1.0],
                        [-1.0, 1.0],
                        [-1.0, -1.0],
                    ]],
                },
            }
        ],
    }


def main() -> int:
    client = TestClient(create_app())

    health = client.get("/healthz")
    health.raise_for_status()
    payload = health.json()
    assert payload["status"] == "ok"
    assert payload["core_version"] == starshine_geo.__version__

    operators = client.get("/api/v1/operators")
    operators.raise_for_status()
    catalog = operators.json()
    assert catalog == starshine_geo.operator_catalog()

    limits = client.get("/api/v1/limits")
    limits.raise_for_status()
    assert limits.json()["workflow_execution_enabled"] is True
    assert limits.json()["inline_preflight"]["max_layers"] == 8
    assert limits.json()["inline_execution"]["mode"] == "isolated_subprocess"
    assert limits.json()["inline_execution"]["timeout_seconds"] == 10

    workbench = client.get("/workbench/")
    workbench.raise_for_status()
    assert "Workflow assurance workbench" in workbench.text
    assert 'src="./app.js"' in workbench.text
    assert 'id="crs-evidence-tab"' in workbench.text

    workbench_script = client.get("/workbench/app.js")
    workbench_script.raise_for_status()
    assert 'from "./api.js"' in workbench_script.text
    assert 'from "./assurance.js"' in workbench_script.text
    assert 'from "./editor.js"' in workbench_script.text
    assert 'from "./render.js"' in workbench_script.text

    workbench_api = client.get("/workbench/api.js")
    workbench_api.raise_for_status()
    assert "/api/v1/limits" in workbench_api.text
    assert "/api/v1/workflows/contract" in workbench_api.text
    assert "/api/v1/workflows/preflight" in workbench_api.text
    assert "/api/v1/workflows/execute" in workbench_api.text

    workbench_render = client.get("/workbench/render.js")
    workbench_render.raise_for_status()
    assert 'from "./render_ui.js"' in workbench_render.text
    assert 'from "./render_review.js"' in workbench_render.text
    assert 'from "./render_editor.js"' in workbench_render.text
    assert 'from "./render_preflight.js"' in workbench_render.text
    assert 'from "./render_assumptions.js"' in workbench_render.text

    workbench_dom = client.get("/workbench/dom.js")
    workbench_dom.raise_for_status()
    assert "textContent" in workbench_dom.text
    assert "innerHTML" not in workbench_dom.text

    for module_name, marker in (
        ("render_ui.js", "initializeTabs"),
        ("render_review.js", "renderReports"),
        ("render_editor.js", "renderStepBuilder"),
        ("render_preflight.js", "renderPreflightReport"),
        ("render_assumptions.js", "renderCrsEvidence"),
        ("render_execution.js", "renderExecutionResult"),
        ("render_preview.js", "renderResultPreview"),
    ):
        module = client.get(f"/workbench/{module_name}")
        module.raise_for_status()
        assert marker in module.text
        assert "/api/v1/" not in module.text
        assert "fetch(" not in module.text

    workbench_editor = client.get("/workbench/editor.js")
    workbench_editor.raise_for_status()
    assert "buildDraftStep" in workbench_editor.text
    assert "appendDraftStep" in workbench_editor.text
    for operator in catalog["operators"]:
        assert f'"{operator["name"]}"' not in workbench_editor.text

    workbench_assurance = client.get("/workbench/assurance.js")
    workbench_assurance.raise_for_status()
    assert "required_external_layers" in workbench_assurance.text
    assert "buildPreflightRequest" in workbench_assurance.text
    assert "FeatureCollection" not in workbench_assurance.text
    assert "geometry" not in workbench_assurance.text.lower()

    workbench_execution = client.get("/workbench/execution.js")
    workbench_execution.raise_for_status()
    assert "buildExecutionRequest" in workbench_execution.text
    assert "assertExecutionEvidenceChain" in workbench_execution.text
    assert "geometry" not in workbench_execution.text.lower()
    assert "fetch(" not in workbench_execution.text

    workbench_preview = client.get("/workbench/preview.js")
    workbench_preview.raise_for_status()
    assert "buildResultPreview" in workbench_preview.text
    assert "fetch(" not in workbench_preview.text
    assert "EPSG" not in workbench_preview.text
    assert "proj4" not in workbench_preview.text.lower()

    workbench_styles = client.get("/workbench/styles.css")
    workbench_styles.raise_for_status()
    assert ".workbench-grid" in workbench_styles.text

    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "clip",
                "inputs": {"input": "source", "mask": "mask"},
                "parameters": {},
                "output": "clipped",
            }
        ],
    }
    review_request = {"workflow": workflow, "layer_names": ["source", "mask"]}

    validation = client.post("/api/v1/workflows/validate", json=review_request)
    validation.raise_for_status()
    assert validation.json() == {"valid": True, "workflow_version": 1}

    plan = client.post("/api/v1/workflows/plan", json=review_request)
    plan.raise_for_status()
    assert plan.json()["required_external_layers"] == ["mask", "source"]
    assert plan.json()["terminal_layers"] == ["clipped"]

    contract = client.post("/api/v1/workflows/contract", json=review_request)
    contract.raise_for_status()
    assert contract.json() == starshine_geo.build_workflow_contract(
        workflow,
        ["source", "mask"],
    )

    graph = client.post("/api/v1/workflows/graph", json=review_request)
    graph.raise_for_status()
    assert graph.json() == starshine_geo.build_workflow_graph(
        workflow,
        ["source", "mask"],
    )

    explanation = client.post("/api/v1/workflows/explain", json=review_request)
    explanation.raise_for_status()
    assert explanation.json() == starshine_geo.explain_workflow(
        workflow,
        ["source", "mask"],
    )

    plan_digest = plan.json()["plan_digest"]
    assert contract.json()["plan_digest"] == plan_digest
    assert graph.json()["plan_digest"] == plan_digest
    assert explanation.json()["plan_digest"] == plan_digest
    assert explanation.json()["graph_digest"] == graph.json()["graph_digest"]

    layers = {"source": _point_layer(), "mask": _mask_layer()}
    preflight = client.post(
        "/api/v1/workflows/preflight",
        json={"workflow": workflow, "layers": layers},
    )
    preflight.raise_for_status()
    assert preflight.json() == starshine_geo.preflight_workflow_inputs(workflow, layers)
    assert preflight.json()["valid"] is True

    execution = client.post(
        "/api/v1/workflows/execute",
        json={
            "workflow": workflow,
            "layers": layers,
            "output_layer": "clipped",
        },
    )
    execution.raise_for_status()
    execution_payload = execution.json()
    expected_context = starshine_geo.run_workflow(workflow, layers)
    expected_result = expected_context["clipped"]
    expected_manifest = starshine_geo.build_manifest(
        workflow,
        layers,
        output_layer_name="clipped",
        output_layer=expected_result,
    )
    assert execution_payload["status"] == "succeeded"
    assert starshine_geo.digest_json(execution_payload["result"]) == starshine_geo.digest_json(
        expected_result
    )
    assert execution_payload["manifest"] == expected_manifest
    assert execution_payload["preflight"] == preflight.json()
    assert execution_payload["execution_policy"]["mode"] == "isolated_subprocess"

    print(
        "Installed Starshine Server bounded-execution smoke passed for "
        f"Starshine Geo {starshine_geo.__version__}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
