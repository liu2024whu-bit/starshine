from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("psutil")

from fastapi.testclient import TestClient

from starshine_server import create_app
from tests.test_core_edge_cases import layer, workflow


@pytest.mark.parametrize("endpoint", ["validate", "plan", "graph", "explain", "contract"])
def test_huge_number_is_structured_http_validation_error(endpoint):
    with TestClient(create_app()) as client:
        response = client.post(f"/api/v1/workflows/{endpoint}", json={
            "workflow": workflow(10**400), "layer_names": ["source"],
        })
    assert response.status_code == 422
    assert response.json()["diagnostic"]["code"] == "invalid_parameter"


@pytest.mark.parametrize("case", ["projection", "group"])
def test_operator_failure_returns_core_error_instead_of_crashed_worker(case):
    value, source = workflow(), layer()
    if case == "group":
        source = layer(properties={"group": ["private-value"]})
        value["steps"][0] = {"operation": "dissolve", "inputs": {"input": "source"},
                              "parameters": {"group_field": "group"}, "output": "result"}
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/workflows/execute", json={
            "workflow": value, "layers": {"source": source}, "output_layer": "result",
        })
    assert response.status_code == 422
    assert response.json()["error"] == "validation"
    assert "private-value" not in response.text
