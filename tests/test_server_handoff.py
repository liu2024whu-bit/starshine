from __future__ import annotations

import importlib.util
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from urllib.error import URLError
from urllib.request import urlopen

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")

ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = ROOT / "examples" / "server_handoff.py"


def _load_client() -> ModuleType:
    spec = importlib.util.spec_from_file_location("starshine_reference_handoff", CLIENT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(base_url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(
                "Uvicorn exited before the reference handoff could start.\n"
                f"stdout:\n{stdout}\nstderr:\n{stderr}"
            )
        try:
            with urlopen(f"{base_url}/healthz", timeout=0.5) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.05)
    raise AssertionError("Timed out waiting for the local Starshine Server.")


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def test_reference_client_uses_only_the_http_boundary() -> None:
    source = CLIENT_PATH.read_text(encoding="utf-8")

    assert "import starshine_geo" not in source
    assert "from starshine_geo" not in source
    assert "import starshine_server" not in source
    assert "from starshine_server" not in source
    assert "urllib.request" in source


def test_reference_handoff_stops_before_execution_when_preflight_fails(tmp_path: Path) -> None:
    client = _load_client()
    called_paths: list[str] = []

    def fake_request(base_url: str, path: str, **kwargs):
        del base_url
        called_paths.append(path)
        if path == "/healthz":
            return {"status": "ok", "api_version": 1, "core_version": "test"}
        if path == "/api/v1/limits":
            return {
                "workflow_execution_enabled": True,
                "inline_execution": {"mode": "isolated_subprocess"},
            }
        if path == "/api/v1/workflows/validate":
            return {"valid": True, "workflow_version": 1}
        if path == "/api/v1/workflows/plan":
            return {"terminal_layers": ["zone_summary"]}
        if path == "/api/v1/workflows/preflight":
            return {"valid": False, "findings": [{"code": "synthetic_failure"}]}
        raise AssertionError((path, kwargs))

    with pytest.raises(client.HandoffError, match="Preflight failed"):
        client.run_handoff(
            "http://unused.invalid",
            tmp_path,
            request_json=fake_request,
        )

    assert "/api/v1/workflows/execute" not in called_paths
    assert not tmp_path.exists()


def test_reference_handoff_runs_against_a_real_uvicorn_process(tmp_path: Path) -> None:
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "starshine_server:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        _wait_for_server(base_url, process)
        completed = subprocess.run(
            [
                sys.executable,
                str(CLIENT_PATH),
                "--base-url",
                base_url,
                "--output-dir",
                str(tmp_path),
            ],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
            timeout=30,
        )
    finally:
        _stop(process)

    assert completed.returncode == 0, completed.stderr
    assert "Reference handoff succeeded" in completed.stdout

    expected_files = {
        "handoff.json",
        "health.json",
        "limits.json",
        "manifest.json",
        "plan.json",
        "preflight.json",
        "result.geojson",
        "validation.json",
    }
    assert {path.name for path in tmp_path.iterdir()} == expected_files

    summary = json.loads((tmp_path / "handoff.json").read_text(encoding="utf-8"))
    preflight = json.loads((tmp_path / "preflight.json").read_text(encoding="utf-8"))
    result = json.loads((tmp_path / "result.geojson").read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    limits = json.loads((tmp_path / "limits.json").read_text(encoding="utf-8"))

    assert summary["status"] == "succeeded"
    assert summary["output_layer"] == "zone_summary"
    assert summary["execution_policy"] == limits["inline_execution"]
    assert preflight["valid"] is True
    assert manifest["output_layer"]["name"] == "zone_summary"

    counts = {
        feature["properties"]["id"]: feature["properties"]["site_count"]
        for feature in result["features"]
    }
    assert counts == {"east": 1, "west": 2}
