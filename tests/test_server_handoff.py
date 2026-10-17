from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
pytest.importorskip("httpx")
pytest.importorskip("psutil")

from scripts.smoke_installed_server import run_reference_handoff

ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = ROOT / "examples" / "server_handoff.py"


def _load_client() -> ModuleType:
    spec = importlib.util.spec_from_file_location("starshine_reference_handoff", CLIENT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
            tmp_path / "run",
            request_json=fake_request,
        )

    assert "/api/v1/workflows/execute" not in called_paths
    assert list(tmp_path.iterdir()) == []


def test_reference_handoff_runs_against_a_real_uvicorn_process(tmp_path: Path) -> None:
    tmp_path = tmp_path / "new-handoff"
    completed = run_reference_handoff(CLIENT_PATH, tmp_path)

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


@pytest.fixture
def handoff_responses():
    import copy

    import starshine_geo as core

    client = _load_client()
    workflow = client._read_json(client._WORKFLOW_PATH)
    layers = {name: client._read_json(path) for name, path in client._LAYER_PATHS.items()}
    plan = core.plan_workflow(workflow, layers)
    preflight = core.preflight_workflow_inputs(workflow, layers)
    result = core.run_workflow(workflow, layers)["zone_summary"]
    manifest = core.build_manifest(
        workflow, layers, output_layer_name="zone_summary", output_layer=result,
    )
    policy = {"mode": "isolated_subprocess"}
    reports = {
        "/healthz": {"status": "ok", "api_version": 1, "core_version": core.__version__},
        "/api/v1/limits": {"workflow_execution_enabled": True, "inline_execution": policy},
        "/api/v1/workflows/validate": {"valid": True, "workflow_version": 1},
        "/api/v1/workflows/plan": plan,
        "/api/v1/workflows/preflight": preflight,
        "/api/v1/workflows/execute": {
            "status": "succeeded", "output_layer": "zone_summary", "preflight": preflight,
            "execution_policy": policy, "result": result, "manifest": manifest,
        },
    }
    calls = []

    def request(base_url, path, **kwargs):
        calls.append(path)
        return copy.deepcopy(reports[path])

    return client, reports, calls, request


@pytest.mark.parametrize("field", ["plan_digest", "workflow_digest"])
def test_mismatched_preflight_cannot_execute(tmp_path, handoff_responses, field):
    client, reports, calls, request = handoff_responses
    reports["/api/v1/workflows/preflight"][field] = "another-run"
    with pytest.raises(client.HandoffError, match="Preflight.*review"):
        client.run_handoff("http://unused.invalid", tmp_path / "run", request_json=request)
    assert "/api/v1/workflows/execute" not in calls
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("field", ["workflow_digest", "starshine_version", "output_layer"])
def test_mismatched_manifest_is_not_published(tmp_path, handoff_responses, field):
    client, reports, calls, request = handoff_responses
    reports["/api/v1/workflows/execute"]["manifest"][field] = "another-run"
    with pytest.raises(client.HandoffError, match="manifest"):
        client.run_handoff("http://unused.invalid", tmp_path / "run", request_json=request)
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("existing", ["file", "empty-directory", "previous-run"])
def test_existing_destination_is_preserved_before_http(tmp_path, handoff_responses, existing):
    client, reports, calls, request = handoff_responses
    output = tmp_path / "run"
    if existing == "file":
        output.write_text("do not replace", encoding="utf-8")
    else:
        output.mkdir()
        if existing == "previous-run":
            (output / "handoff.json").write_text("previous evidence", encoding="utf-8")
    with pytest.raises(client.HandoffError, match="new output directory"):
        client.run_handoff("http://unused.invalid", output, request_json=request)
    assert calls == []
    if existing == "file":
        assert output.read_text(encoding="utf-8") == "do not replace"
    elif existing == "previous-run":
        assert (output / "handoff.json").read_text(encoding="utf-8") == "previous evidence"
    else:
        assert list(output.iterdir()) == []


def test_write_failure_never_publishes_success_marker(tmp_path, handoff_responses, monkeypatch):
    client, reports, calls, request = handoff_responses
    original = client._write_json

    def fail(path, value):
        if path.name == "result.geojson":
            raise OSError("synthetic disk failure")
        original(path, value)

    monkeypatch.setattr(client, "_write_json", fail)
    with pytest.raises(client.HandoffError, match="write handoff"):
        client.run_handoff("http://unused.invalid", tmp_path / "run", request_json=request)
    assert not (tmp_path / "run" / "handoff.json").exists()


def test_new_destination_collision_during_http_does_not_overwrite(tmp_path, handoff_responses):
    client, reports, calls, request = handoff_responses
    output = tmp_path / "run"

    def concurrent(base, path, **kwargs):
        if path == "/api/v1/workflows/execute":
            output.mkdir()
            (output / "handoff.json").write_text("other run", encoding="utf-8")
        return request(base, path, **kwargs)

    with pytest.raises(client.HandoffError, match="new output directory"):
        client.run_handoff("http://unused.invalid", output, request_json=concurrent)
    assert (output / "handoff.json").read_text(encoding="utf-8") == "other run"


def test_response_read_is_bounded_before_json_parsing(monkeypatch):
    import io

    client = _load_client()
    seen = []

    class Response(io.BytesIO):
        def read(self, size=-1):
            seen.append(size)
            return super().read(size)

    monkeypatch.setattr(client, "_MAX_RESPONSE_BYTES", 8, raising=False)
    monkeypatch.setattr(client, "urlopen", lambda *a, **k: Response(b'{"long": "value"}'))
    with pytest.raises(client.HandoffError, match="response byte limit"):
        client._request_json("http://unused.invalid", "/healthz")
    assert seen == [9]


def test_http_error_body_is_closed_without_reading_or_echoing(monkeypatch):
    import io
    from urllib.error import HTTPError

    client = _load_client()

    class Body(io.BytesIO):
        def read(self, *args):
            raise AssertionError("error response body must not be read")

    body = Body(b"synthetic sensitive diagnostic")

    def failure(*args, **kwargs):
        raise HTTPError("http://unused.invalid", 500, "error", {}, body)

    monkeypatch.setattr(client, "urlopen", failure)
    with pytest.raises(client.HandoffError, match="HTTP 500") as caught:
        client._request_json("http://unused.invalid", "/healthz")
    assert "sensitive" not in str(caught.value)
    assert body.closed


@pytest.mark.parametrize("body", [b'{"x":NaN}', b'{"x":1e10000}', b'{"x":', b'[]'])
def test_invalid_response_is_not_evidence(monkeypatch, body):
    import io

    client = _load_client()
    monkeypatch.setattr(client, "urlopen", lambda *a, **k: io.BytesIO(body))
    with pytest.raises(client.HandoffError, match="JSON"):
        client._request_json("http://unused.invalid", "/healthz")


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout_stops_before_http(tmp_path, handoff_responses, timeout):
    client, reports, calls, request = handoff_responses
    with pytest.raises(client.HandoffError, match="timeout"):
        client.run_handoff("http://unused.invalid", tmp_path / "run", timeout=timeout,
                           request_json=request)
    assert calls == []


def test_cli_reports_expected_failure_without_traceback(tmp_path, capsys):
    client = _load_client()
    result = client.main(["--output-dir", str(tmp_path / "run"), "--timeout", "0"])
    assert result == 1
    captured = capsys.readouterr()
    assert "timeout" in captured.err
    assert "Traceback" not in captured.err
    assert "succeeded" not in captured.out
