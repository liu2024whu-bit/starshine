from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import urlopen

import psutil
from fastapi.testclient import TestClient

import starshine_geo
from starshine_server import create_app
from starshine_server.execution import ExecutionBoundaryError, _supervise_process


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


def run_reference_handoff(client_script: Path, output_dir: Path) -> subprocess.CompletedProcess[str]:
    """Exercise the standard-library client against an actual installed Server socket."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [sys.executable, "-I", "-m", "uvicorn", "starshine_server:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        while True:
            if process.poll() is not None:
                raise AssertionError("Installed Server exited before the reference handoff.")
            try:
                with urlopen(f"{base_url}/healthz", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except (OSError, URLError):
                pass
            if time.monotonic() >= deadline:
                raise AssertionError("Installed Server did not become ready in time.")
            time.sleep(0.05)
        completed = subprocess.run(
            [sys.executable, "-I", str(client_script), "--base-url", base_url,
             "--output-dir", str(output_dir)],
            capture_output=True, text=True, timeout=30, check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        return completed
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def main() -> int:
    client = TestClient(create_app())

    health = client.get("/healthz")
    health.raise_for_status()
    payload = health.json()
    assert payload["status"] == "ok"
    assert payload["core_version"] == starshine_geo.__version__

    # Exercise the installed middleware, not only source-checkout boundary tests.
    oversized = client.post(
        "/api/v1/workflows/preflight",
        content=iter([b"x" * (2 * 1024 * 1024), b"x"]),
        headers={"content-type": "application/json"},
    )
    assert oversized.status_code == 413
    assert oversized.json()["code"] == "request_body_too_large"
    invalid_number = client.post(
        "/api/v1/workflows/preflight",
        content=b'{"workflow":NaN}',
        headers={"content-type": "application/json"},
    )
    assert invalid_number.status_code == 400
    assert invalid_number.json()["error"] == "invalid_json"

    execution_invalid_number = client.post(
        "/api/v1/workflows/execute",
        content=b'{"workflow":NaN}',
        headers={"content-type": "application/json"},
    )
    assert execution_invalid_number.status_code == 400
    assert execution_invalid_number.json()["error"] == "invalid_json"

    # Prove the installed supervisor also stops on unavailable monitoring.
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with patch(
            "starshine_server.execution._process_tree_rss",
            side_effect=psutil.AccessDenied(pid=child.pid),
        ):
            try:
                _supervise_process(child, timeout_seconds=2, memory_limit_bytes=512 * 1024 * 1024)
            except ExecutionBoundaryError as exc:
                assert exc.code == "worker_supervision_failed"
            else:
                raise AssertionError("monitoring failure must stop execution")
        assert child.returncode is not None
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=2)

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

    # The same artifact includes the fixed client and its synthetic inputs, not a source checkout.
    client_script = Path(__file__).resolve().parents[1] / "examples" / "server_handoff.py"
    with tempfile.TemporaryDirectory(prefix="starshine-handoff-") as directory:
        output = Path(directory) / "evidence"
        run_reference_handoff(client_script, output)
        handoff_result = json.loads((output / "result.geojson").read_text(encoding="utf-8"))
        assert {feature["properties"]["id"]: feature["properties"]["site_count"]
                for feature in handoff_result["features"]} == {"east": 1, "west": 2}
        assert json.loads((output / "handoff.json").read_text(encoding="utf-8"))["status"] == "succeeded"

    print(
        "Installed Starshine Server bounded-execution smoke passed for "
        f"Starshine Geo {starshine_geo.__version__}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
