from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("psutil")
pytest.importorskip("fastapi")

from scripts import observe_macos_decision_poll as experiment

SECRET = "private experiment detail must not escape"
REVISION = "a" * 40
ZERO = {"poll_path": "zero", "poll_result": "none", "waitpid_calls": 1}


def report():
    return {"samples": [], "stop_reason": "not_started", "observation": "incomplete"}


def success(request, expected):
    result = experiment.starshine_geo.run_workflow(request["workflow"], request["layers"])["clipped"]
    return httpx.Response(200, json={
        "status": "succeeded", "output_layer": "clipped", "result": result,
        "manifest": expected["manifest"], "preflight": expected["preflight"],
        "execution_policy": expected["policy"],
    })


def failure(code="worker_supervision_failed", **kwargs):
    return httpx.Response(500, json={
        "error": "execution_boundary", "code": code, "reason": "missing",
        "stage": "tree_memory", "message": SECRET, **kwargs,
    })


def run_control(monkeypatch, tmp_path, responses):
    request, expected = experiment._fixture()
    output = tmp_path / "evidence.json"
    evidence = report()
    state = {"calls": 0, "observations": None}

    @contextmanager
    def observe(execution, observations):
        state["observations"] = observations
        yield

    def post(route, *, json):
        import json as codec

        assert route == "/api/v1/workflows/execute" and json is request
        # The next attempt must already be on disk, without fabricated completion.
        persisted = codec.loads(output.read_text(encoding="utf-8"))
        assert persisted["samples"][-1] == {
            "sample": state["calls"] + 1, "outcome": "started",
        }
        response, observation = responses[state["calls"]]
        state["calls"] += 1
        if observation is not None:
            state["observations"].append(observation)
        return success(request, expected) if response == "success" else response

    monkeypatch.setattr(experiment, "observe_supervision", observe)
    monkeypatch.setattr(experiment, "SAMPLES", len(responses))
    result = experiment._run_samples(SimpleNamespace(post=post), request, expected, evidence, output)
    assert json.loads(output.read_text(encoding="utf-8")) == evidence
    assert SECRET not in output.read_text(encoding="utf-8")
    return result, evidence, state["calls"]


def test_fixed_design_has_50_samples_and_success_is_inconclusive(monkeypatch, tmp_path):
    assert experiment.SAMPLES == 50
    result, evidence, calls = run_control(monkeypatch, tmp_path, [
        ("success", None),
        ("success", {"poll_path": "terminal", "poll_result": "terminal", "waitpid_calls": 0}),
    ])
    assert result == 0 and calls == 2
    assert evidence["observation"] == "no_recurrence_inconclusive"
    assert evidence["stop_reason"] == "fixed_sample_complete"


def test_known_failure_is_retained_and_remains_fatal_after_later_success(monkeypatch, tmp_path):
    result, evidence, calls = run_control(monkeypatch, tmp_path, [
        ("success", None), (failure(), ZERO), ("success", None),
    ])
    assert result == 1 and calls == 3
    assert evidence["observation"] == "recurrence_or_failure_observed"
    assert evidence["stop_reason"] == "fixed_sample_complete"
    assert evidence["samples"][1]["decision_poll"] == ZERO
    assert evidence["samples"][1]["code"] == "worker_supervision_failed"


@pytest.mark.parametrize("response,observation,stop", [
    (failure("worker_cleanup_failed"), None, "cleanup_failed"),
    (failure("worker_failed"), None, "unclassified_failure"),
    (failure(code=SECRET), None, "unclassified_failure"),
    (failure(), None, "unclassified_failure"),
    (failure(stage="process_lookup"), ZERO, "unclassified_failure"),
    (httpx.Response(200, content=b"null"), None, "unexpected_evidence"),
])
def test_cleanup_or_unclassified_failure_stops_incomplete(
    monkeypatch, tmp_path, response, observation, stop,
):
    result, evidence, calls = run_control(monkeypatch, tmp_path, [
        (response, observation), ("success", None),
    ])
    assert result == 1 and calls == 1
    assert evidence["observation"] == "incomplete" and evidence["stop_reason"] == stop


def test_actual_core_http_serialization_uses_canonical_digest(monkeypatch):
    from fastapi.testclient import TestClient

    request, expected = experiment._fixture()
    core_result = experiment.starshine_geo.run_workflow(
        request["workflow"], request["layers"],
    )["clipped"]
    monkeypatch.setattr(experiment.execution, "_run_worker", lambda payload: {
        "status": "ok", "result": core_result, "manifest": expected["manifest"],
    })
    response = TestClient(experiment.create_app()).post(
        "/api/v1/workflows/execute", json=request,
    )
    assert response.status_code == 200
    assert response.json()["result"] != core_result  # Tuple coordinates became JSON arrays.
    assert all(experiment._evidence_checks(response.json(), expected).values())


@pytest.mark.parametrize("field", [
    "status", "output_layer", "result", "manifest", "preflight", "execution_policy",
])
def test_success_evidence_rejects_each_mismatch(field):
    request, expected = experiment._fixture()
    payload = success(request, expected).json()
    payload[field] = None
    assert not all(experiment._evidence_checks(payload, expected).values())


def test_unsupported_environment_starts_no_worker_and_never_prints_raw_error(
    monkeypatch, tmp_path, capsys,
):
    output = tmp_path / "evidence.json"

    def unsupported():
        raise RuntimeError(SECRET)

    def forbidden():
        pytest.fail("unsupported environment must not prepare execution")

    monkeypatch.setattr(experiment, "_require_environment", unsupported)
    monkeypatch.setattr(experiment, "_fixture", forbidden)
    assert experiment.main([
        "--wheel", "missing.whl", "--revision", REVISION, "--output", str(output),
    ]) == 1
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["samples"] == [] and evidence["observation"] == "incomplete"
    assert evidence["rss_substage_observed"] is False
    assert "exact_runtime_guard_passed" not in evidence
    assert SECRET not in capsys.readouterr().out
    assert SECRET not in output.read_text(encoding="utf-8")


def test_existing_evidence_is_not_overwritten_before_guard(monkeypatch, tmp_path):
    output = tmp_path / "evidence.json"
    output.write_text(SECRET, encoding="utf-8")
    monkeypatch.setattr(experiment, "_require_environment", lambda: pytest.fail("guard called"))
    assert experiment.main([
        "--wheel", "missing.whl", "--revision", REVISION, "--output", str(output),
    ]) == 1
    assert output.read_text(encoding="utf-8") == SECRET


def test_unexpected_request_exception_retains_started_attempt_and_stops(
    monkeypatch, tmp_path, capsys,
):
    output = tmp_path / "evidence.json"
    calls = []

    @contextmanager
    def client_context(app):
        def post(*args, **kwargs):
            calls.append(1)
            assert json.loads(output.read_text())["samples"][-1]["outcome"] == "started"
            raise RuntimeError(SECRET)

        yield SimpleNamespace(post=post)

    monkeypatch.setattr(experiment, "_require_environment", lambda: None)
    monkeypatch.setattr(experiment, "_verify_wheel", lambda *args: {
        "revision": REVISION, "wheel_sha256": "b" * 64,
    })
    monkeypatch.setattr(experiment, "TestClient", client_context)
    assert experiment.main([
        "--wheel", "missing.whl", "--revision", REVISION, "--output", str(output),
    ]) == 1
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert calls == [1] and evidence["observation"] == "incomplete"
    assert evidence["stop_reason"] == "harness_error"
    assert evidence["samples"] == [{"sample": 1, "outcome": "unexpected_exception"}]
    assert SECRET not in capsys.readouterr().out


def test_atomic_evidence_write_failure_preserves_previous_report(monkeypatch, tmp_path):
    output = tmp_path / "evidence.json"
    output.write_text("previous report", encoding="utf-8")

    def unavailable(*args):
        raise OSError(SECRET)

    monkeypatch.setattr(experiment.os, "replace", unavailable)
    with pytest.raises(OSError):
        experiment._write_report(output, report())
    assert output.read_text(encoding="utf-8") == "previous report"
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize("tamper", [False, True])
def test_provenance_checks_all_installed_package_files(monkeypatch, tmp_path, tamper):
    prefix = tmp_path / "venv"
    site = prefix / "site-packages"
    files = {
        "starshine_geo/__init__.py": b"core",
        "starshine_server/execution.py": b"supervisor",
        "starshine_server/worker.py": b"worker",
    }
    wheel = tmp_path / "candidate.whl"
    with ZipFile(wheel, "w") as archive:
        for name, data in files.items():
            path = site / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"changed" if tamper and name.endswith("worker.py") else data)
            archive.writestr(name, data)
    monkeypatch.setattr(experiment.sys, "prefix", str(prefix))
    monkeypatch.setattr(experiment.metadata, "distribution", lambda name: SimpleNamespace(
        locate_file=lambda name: site / name,
    ))
    monkeypatch.setattr(experiment, "starshine_geo", SimpleNamespace(
        __file__=str(site / "starshine_geo/__init__.py"),
    ))
    monkeypatch.setattr(experiment, "execution", SimpleNamespace(
        __file__=str(site / "starshine_server/execution.py"),
    ))
    if tamper:
        with pytest.raises(RuntimeError, match="^candidate_wheel_content_mismatch$"):
            experiment._verify_wheel(wheel, REVISION)
    else:
        result = experiment._verify_wheel(wheel, REVISION)
        assert result["revision"] == REVISION and len(result["wheel_sha256"]) == 64


def test_invalid_revision_is_refused_before_wheel_io():
    with pytest.raises(RuntimeError, match="^invalid_candidate_revision$"):
        experiment._verify_wheel(Path("missing.whl"), SECRET)
