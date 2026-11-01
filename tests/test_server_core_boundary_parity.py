from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("psutil")

from fastapi.testclient import TestClient
from test_core_boundary_parity import OPERATIONS, identifier_case, reproject_case

from starshine_server import create_app


@pytest.mark.parametrize("operation", OPERATIONS)
def test_signed_zero_identifiers_execute_in_isolated_http_worker(operation):
    workflow, layers, output = identifier_case(operation, [-0.0, 0.0])
    response = TestClient(create_app()).post("/api/v1/workflows/execute", json={
        "workflow": workflow, "layers": layers, "output_layer": "out",
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["preflight"]["valid"]
    assert json.dumps([
        item["properties"][output] for item in payload["result"]["features"]
    ]) == "[-0.0, 0.0]"


def test_unavailable_coordinate_operation_is_http_validation_not_worker_failure():
    workflow, source = reproject_case()
    response = TestClient(create_app()).post("/api/v1/workflows/execute", json={
        "workflow": workflow, "layers": {"source": source}, "output_layer": "out",
    })
    assert response.status_code == 422
    assert "transformation could not be created" in response.json()["message"]
    assert "Synthetic local grid" not in response.text
