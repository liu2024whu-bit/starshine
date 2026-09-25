from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

import starshine_geo
from starshine_server import create_app
from starshine_server.limits import MAX_FEATURES_PER_LAYER, MAX_REQUEST_BYTES

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

POINT_LAYER = {
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


def test_limits_endpoint_makes_the_inline_boundary_client_visible() -> None:
    response = _client().get("/api/v1/limits")

    assert response.status_code == 200
    assert response.json() == {
        "inline_preflight": {
            "max_request_bytes": 2 * 1024 * 1024,
            "max_layers": 8,
            "max_layer_name_chars": 128,
            "max_workflow_steps": 16,
            "max_features_per_layer": 2_000,
            "max_total_features": 5_000,
        },
        "workflow_execution_enabled": False,
    }


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


def test_preflight_endpoint_returns_the_canonical_core_report() -> None:
    payload = {
        "workflow": VALID_WORKFLOW,
        "layers": {"source": POINT_LAYER},
    }

    response = _client().post("/api/v1/workflows/preflight", json=payload)

    assert response.status_code == 200
    assert response.json() == starshine_geo.preflight_workflow_inputs(
        VALID_WORKFLOW,
        {"source": POINT_LAYER},
    )
    assert response.json()["valid"] is True
    assert response.json()["checked_layer_count"] == 1


def test_preflight_keeps_data_failures_in_the_canonical_report() -> None:
    invalid_layer = {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:4326",
        "features": "not-a-list",
    }

    response = _client().post(
        "/api/v1/workflows/preflight",
        json={"workflow": VALID_WORKFLOW, "layers": {"source": invalid_layer}},
    )

    assert response.status_code == 200
    report = response.json()
    assert report["valid"] is False
    assert report["error_count"] == 1
    assert report["findings"][0]["code"] == "invalid_feature_collection"


def test_preflight_rejects_feature_counts_above_the_service_boundary() -> None:
    feature = POINT_LAYER["features"][0]
    oversized_layer = {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:4326",
        "features": [feature for _ in range(MAX_FEATURES_PER_LAYER + 1)],
    }

    response = _client().post(
        "/api/v1/workflows/preflight",
        json={"workflow": VALID_WORKFLOW, "layers": {"source": oversized_layer}},
    )

    assert response.status_code == 413
    assert response.json()["error"] == "request_limit"
    assert response.json()["code"] == "too_many_features_in_layer"
    assert response.json()["limit"] == MAX_FEATURES_PER_LAYER
    assert response.json()["actual"] == MAX_FEATURES_PER_LAYER + 1


def test_server_rejects_http_bodies_above_the_declared_byte_limit() -> None:
    response = _client().post(
        "/api/v1/workflows/preflight",
        content="x" * (MAX_REQUEST_BYTES + 1),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "request_body_too_large"
    assert response.json()["limit"] == MAX_REQUEST_BYTES


def test_expected_core_validation_errors_have_a_stable_http_boundary(monkeypatch) -> None:
    def fail_preflight(*args, **kwargs):
        del args, kwargs
        raise starshine_geo.ValidationError("synthetic expected validation failure")

    monkeypatch.setattr(starshine_geo, "preflight_workflow_inputs", fail_preflight)

    response = _client().post(
        "/api/v1/workflows/preflight",
        json={"workflow": VALID_WORKFLOW, "layers": {"source": POINT_LAYER}},
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": "validation",
        "message": "synthetic expected validation failure",
    }


def test_preflight_endpoint_never_executes_the_workflow(monkeypatch) -> None:
    def forbidden_execution(*args, **kwargs):
        del args, kwargs
        raise AssertionError("Preflight must not execute spatial operators")

    monkeypatch.setattr(starshine_geo, "run_workflow", forbidden_execution)

    response = _client().post(
        "/api/v1/workflows/preflight",
        json={"workflow": VALID_WORKFLOW, "layers": {"source": POINT_LAYER}},
    )

    assert response.status_code == 200
    assert response.json()["valid"] is True
