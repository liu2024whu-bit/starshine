from __future__ import annotations

import subprocess
import sys

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("psutil")

from fastapi.testclient import TestClient

import starshine_geo
import starshine_server.execution as execution_module
from starshine_server import create_app
from starshine_server.execution import ExecutionBoundaryError, _supervise_process
from starshine_server.limits import (
    MAX_EXECUTION_MEMORY_BYTES,
    MAX_EXECUTION_RESPONSE_BYTES,
    MAX_EXECUTION_SECONDS,
)

WORKFLOW = {
    "version": 1,
    "steps": [
        {
            "operation": "buffer",
            "inputs": {"input": "source"},
            "parameters": {
                "distance": 100,
                "source_crs": "EPSG:4326",
                "work_crs": "EPSG:3857",
            },
            "output": "buffered",
        }
    ],
}

LAYER = {
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


def test_execute_endpoint_returns_core_result_and_manifest() -> None:
    response = _client().post(
        "/api/v1/workflows/execute",
        json={
            "workflow": WORKFLOW,
            "layers": {"source": LAYER},
            "output_layer": "buffered",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    expected_context = starshine_geo.run_workflow(WORKFLOW, {"source": LAYER})
    expected_result = expected_context["buffered"]
    expected_manifest = starshine_geo.build_manifest(
        WORKFLOW,
        {"source": LAYER},
        output_layer_name="buffered",
        output_layer=expected_result,
    )

    assert payload["status"] == "succeeded"
    assert payload["output_layer"] == "buffered"
    # HTTP JSON normalizes geometry coordinate tuples to arrays; compare canonical JSON semantics.
    assert starshine_geo.digest_json(payload["result"]) == starshine_geo.digest_json(expected_result)
    assert payload["manifest"] == expected_manifest
    assert payload["preflight"] == starshine_geo.preflight_workflow_inputs(
        WORKFLOW,
        {"source": LAYER},
    )
    assert payload["execution_policy"] == {
        "mode": "isolated_subprocess",
        "timeout_seconds": MAX_EXECUTION_SECONDS,
        "memory_limit_bytes": MAX_EXECUTION_MEMORY_BYTES,
        "max_response_bytes": MAX_EXECUTION_RESPONSE_BYTES,
    }


def test_failed_preflight_never_starts_the_execution_worker(monkeypatch) -> None:
    started = False

    def forbidden_worker(payload):
        nonlocal started
        started = True
        raise AssertionError(payload)

    monkeypatch.setattr(execution_module, "_run_worker", forbidden_worker)
    invalid_layer = {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:4326",
        "features": "not-a-list",
    }

    response = _client().post(
        "/api/v1/workflows/execute",
        json={
            "workflow": WORKFLOW,
            "layers": {"source": invalid_layer},
            "output_layer": "buffered",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"] == "preflight_failed"
    assert response.json()["preflight"]["valid"] is False
    assert started is False


def test_execute_requires_a_produced_output_layer() -> None:
    response = _client().post(
        "/api/v1/workflows/execute",
        json={
            "workflow": WORKFLOW,
            "layers": {"source": LAYER},
            "output_layer": "source",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": "validation",
        "message": "output_layer must name a layer produced by the Workflow",
    }


def test_process_supervisor_enforces_wall_clock_timeout() -> None:
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with pytest.raises(ExecutionBoundaryError) as exc_info:
        _supervise_process(
            child,
            timeout_seconds=0.05,
            memory_limit_bytes=MAX_EXECUTION_MEMORY_BYTES,
        )

    assert exc_info.value.code == "execution_timeout"
    assert child.poll() is not None


def test_process_supervisor_enforces_memory_limit() -> None:
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with pytest.raises(ExecutionBoundaryError) as exc_info:
        _supervise_process(
            child,
            timeout_seconds=2,
            memory_limit_bytes=1,
        )

    assert exc_info.value.code == "execution_memory_limit"
    assert child.poll() is not None
