from __future__ import annotations

from fastapi.testclient import TestClient

import starshine_geo
from starshine_server import create_app

VALID_WORKFLOW = {
    "version": 1,
    "steps": [
        {
            "operation": "buffer",
            "inputs": {"input": "source"},
            "parameters": {
                "distance": 10,
                "source_crs": "EPSG:4326",
                "work_crs": "EPSG:3857",
            },
            "output": "buffered",
        }
    ],
}


def _client() -> TestClient:
    return TestClient(create_app())


def test_health_reports_server_and_core_versions() -> None:
    response = _client().get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "starshine-server",
        "api_version": 1,
        "core_version": starshine_geo.__version__,
    }


def test_operator_endpoint_reuses_public_core_catalog() -> None:
    response = _client().get("/api/v1/operators")

    assert response.status_code == 200
    assert response.json() == starshine_geo.operator_catalog()
    assert "buffer" in {item["name"] for item in response.json()["operators"]}


def test_validate_endpoint_accepts_a_valid_data_free_workflow() -> None:
    response = _client().post(
        "/api/v1/workflows/validate",
        json={"workflow": VALID_WORKFLOW, "layer_names": ["source"]},
    )

    assert response.status_code == 200
    assert response.json() == {"valid": True, "workflow_version": 1}


def test_validate_endpoint_preserves_core_diagnostics() -> None:
    invalid = {
        "version": 1,
        "steps": [
            {
                "operation": "buffer",
                "inputs": {"input": "source"},
                "parameters": {
                    "distance": 10,
                    "source_crs": "EPSG:4326",
                },
                "output": "buffered",
            }
        ],
    }

    response = _client().post(
        "/api/v1/workflows/validate",
        json={"workflow": invalid, "layer_names": ["source"]},
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": "workflow_validation",
        "diagnostic": {
            "code": "missing_parameter",
            "message": "missing required parameter for buffer: work_crs",
            "path": "steps[0].parameters.work_crs",
            "step_index": 0,
            "operation": "buffer",
        },
    }


def test_plan_endpoint_is_deterministic_and_uses_the_core_plan() -> None:
    payload = {"workflow": VALID_WORKFLOW, "layer_names": ["source"]}

    first = _client().post("/api/v1/workflows/plan", json=payload)
    second = _client().post("/api/v1/workflows/plan", json=payload)

    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json() == starshine_geo.plan_workflow(VALID_WORKFLOW, ["source"])
    assert first.json()["terminal_layers"] == ["buffered"]
