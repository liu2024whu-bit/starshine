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
