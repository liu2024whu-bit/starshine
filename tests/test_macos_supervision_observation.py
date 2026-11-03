from __future__ import annotations

import json

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")
pytest.importorskip("psutil")

from scripts import diagnose_macos_supervision as observation


class Client:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = 0

    def post(self, *_args, **_kwargs):
        self.calls += 1
        value = next(self.replies)
        if isinstance(value, Exception):
            raise value
        return value


def test_fixed_50_no_retry_and_every_failure_retained(tmp_path, monkeypatch):
    monkeypatch.setattr(observation, "_observe", lambda response, expected: response)
    client = Client([{"outcome": "failed", "code": "worker_supervision_failed"}] + [{"outcome": "succeeded"} for _ in range(49)])
    output = tmp_path / "evidence.json"
    assert observation.run(client, output, supported=True) == 1
    report = json.loads(output.read_text())
    assert client.calls == 50
    assert len(report["samples"]) == 50
    assert report["samples"][0]["outcome"] == "failed"
    assert report["stop_reason"] == "fixed_sample_complete"
    assert report["resolves_issue_187"] is False


def test_complete_success_is_inconclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(observation, "_observe", lambda response, expected: response)
    output = tmp_path / "evidence.json"
    assert observation.run(Client([{"outcome": "succeeded"} for _ in range(50)]),
                           output, supported=True) == 0
    assert json.loads(output.read_text())["observation"] == "no_recurrence_inconclusive"


@pytest.mark.parametrize("reply, reason", [
    ({"outcome": "failed", "code": "worker_cleanup_failed"}, "unconfirmed_cleanup"),
    (RuntimeError("SECRET /private/path pid=123"), "unexpected_harness_error"),
])
def test_stops_on_unknown_cleanup_or_unexpected_error(tmp_path, monkeypatch, reply, reason):
    monkeypatch.setattr(observation, "_observe", lambda response, expected: response)
    output = tmp_path / "evidence.json"
    client = Client([reply])
    assert observation.run(client, output, supported=True) == 1
    report = json.loads(output.read_text())
    assert client.calls == 1
    assert report["observation"] == "incomplete"
    assert report["stop_reason"] == reason
    assert "SECRET" not in output.read_text()


def test_unsupported_never_starts_worker(tmp_path):
    output = tmp_path / "evidence.json"
    assert observation.run(None, output, supported=False) == 1
    assert json.loads(output.read_text())["stop_reason"] == "unsupported_environment"


@pytest.mark.parametrize("payload", [
    {"error": "execution_boundary", "code": "worker_supervision_failed", "reason": [],
     "stage": {}, "substage": "SECRET", "message": "SECRET", "pid": 123},
    {"error": "SECRET", "code": "worker_cleanup_failed"}, ["SECRET"],
])
def test_diagnostics_do_not_echo_untrusted_payload(payload):
    row = observation._observe(httpx.Response(500, json=payload), {})
    assert "SECRET" not in json.dumps(row)
    assert "pid" not in row
    assert "message" not in row


def test_retains_fixed_substage():
    row = observation._observe(httpx.Response(500, json={
        "error": "execution_boundary", "code": "worker_supervision_failed",
        "reason": "missing", "stage": "tree_memory", "substage": "children_enumeration",
    }), {})
    assert row["substage"] == "children_enumeration"


def test_incremental_evidence_exists_before_next_sample(tmp_path, monkeypatch):
    output = tmp_path / "evidence.json"
    monkeypatch.setattr(observation, "_observe", lambda response, expected: response)

    class Incremental(Client):
        def post(self, *args, **kwargs):
            assert len(json.loads(output.read_text())["samples"]) == self.calls + 1
            return super().post(*args, **kwargs)

    assert observation.run(Incremental([{"outcome": "succeeded"} for _ in range(50)]),
                           output, supported=True) == 0


def test_unknown_http_failure_stops_incomplete(tmp_path):
    output = tmp_path / "evidence.json"
    client = Client([httpx.Response(500, text="SECRET")])
    assert observation.run(client, output, supported=True) == 1
    assert json.loads(output.read_text())["stop_reason"] == "unclassified_response"
    assert client.calls == 1


def test_source_checkout_is_not_installed_candidate():
    assert observation._installed_candidate() is False


def test_shutdown_error_preserves_all_samples(tmp_path, monkeypatch):
    output = tmp_path / "evidence.json"
    monkeypatch.setattr(observation, "EVIDENCE", output)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "candidate.whl").write_bytes(b"fixture")
    monkeypatch.setenv("STARSHINE_OBSERVATION_REVISION", "a" * 40)
    monkeypatch.setattr(observation, "_environment_supported", lambda: True)
    monkeypatch.setattr(observation, "_installed_candidate", lambda: True)
    monkeypatch.setattr(observation, "_observe", lambda response, expected: response)

    class Context(Client):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            raise RuntimeError("SECRET")

    monkeypatch.setattr(observation, "TestClient", lambda app: Context(
        [{"outcome": "succeeded"} for _ in range(50)]))
    assert observation.main() == 1
    report = json.loads(output.read_text())
    assert len(report["samples"]) == 50
    assert report["observation"] == "incomplete"
    assert "SECRET" not in output.read_text()


def test_real_success_response_validation():
    expected = {"result": {"type": "FeatureCollection"}, "manifest": {"version": 1},
                "preflight": {"valid": True}}
    payload = {**expected, "status": "succeeded",
               "execution_policy": {"mode": "isolated_subprocess"}}
    assert observation._observe(httpx.Response(200, json=payload), expected) == {
        "outcome": "succeeded", "http_status": 200, "evidence_matches": True,
        "status_matches": True, "result_digest_matches": True, "manifest_matches": True,
        "preflight_matches": True, "execution_mode_matches": True,
    }
    payload["manifest"] = {}
    assert observation._observe(httpx.Response(200, json=payload), expected)["outcome"] == "failed"


@pytest.mark.parametrize("payload", [{}, [], {"status": "succeeded"}])
def test_malformed_success_stops(tmp_path, payload):
    output = tmp_path / "evidence.json"
    client = Client([httpx.Response(200, json=payload)])
    assert observation.run(client, output, supported=True) == 1
    report = json.loads(output.read_text())
    assert report["observation"] == "incomplete"
    assert client.calls == 1


def test_real_testclient_json_roundtrip_preserves_core_digest(monkeypatch):
    # Real HTTP serialization of a real Core result, not a handcrafted tuple fixture.
    import importlib

    request = observation._request()
    result = observation.starshine_geo.run_workflow(
        request["workflow"], request["layers"],
    )["clipped"]
    expected = {
        "result": result,
        "manifest": observation.starshine_geo.build_manifest(
            request["workflow"], request["layers"],
            output_layer_name="clipped", output_layer=result,
        ),
        "preflight": observation.starshine_geo.preflight_workflow_inputs(
            request["workflow"], request["layers"],
        ),
    }
    payload = {**expected, "status": "succeeded",
               "execution_policy": {"mode": "isolated_subprocess"}}
    app_module = importlib.import_module("starshine_server.app")
    monkeypatch.setattr(app_module, "execute_inline_workflow", lambda *a, **kw: payload)
    with observation.TestClient(observation.create_app()) as client:
        response = client.post("/api/v1/workflows/execute", json=request)
    assert response.status_code == 200
    assert response.json()["result"] != expected["result"]  # tuples become JSON arrays
    row = observation._observe(response, expected)
    assert row["outcome"] == "succeeded"
    assert row["result_digest_matches"] is True
    assert row["evidence_matches"] is True


@pytest.mark.parametrize("field, changed, comparison", [
    ("status", "failed", "status_matches"),
    ("result", {"changed": True}, "result_digest_matches"),
    ("manifest", {"changed": True}, "manifest_matches"),
    ("preflight", {"valid": False}, "preflight_matches"),
    ("execution_policy", {"mode": "other"}, "execution_mode_matches"),
])
def test_each_original_acceptance_comparison_remains_required(field, changed, comparison):
    expected = {"result": {"coordinates": (0.0, 0.0)}, "manifest": {"version": 1},
                "preflight": {"valid": True}}
    payload = {**expected, "status": "succeeded",
               "execution_policy": {"mode": "isolated_subprocess"}}
    payload[field] = changed
    row = observation._observe(httpx.Response(200, json=payload), expected)
    assert row[comparison] is False
    assert row["outcome"] == "failed"
    assert row["evidence_matches"] is False
    assert sum(row[key] is False for key in (
        "status_matches", "result_digest_matches", "manifest_matches", "preflight_matches",
        "execution_mode_matches",
    )) == 1
