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


@pytest.mark.parametrize("failing_read", ["root_memory", "children", "descendant_memory"])
def test_live_process_inspection_failure_is_not_zero_memory(failing_read) -> None:
    from types import SimpleNamespace

    import psutil

    def denied(*args, **kwargs):
        raise psutil.AccessDenied(pid=123456)

    descendant = SimpleNamespace(memory_info=lambda: SimpleNamespace(rss=3))
    process = SimpleNamespace(
        memory_info=lambda: SimpleNamespace(rss=7),
        children=lambda **kwargs: [descendant],
    )
    if failing_read == "root_memory":
        process.memory_info = denied
    elif failing_read == "children":
        process.children = denied
    else:
        descendant.memory_info = denied

    with pytest.raises(psutil.AccessDenied):
        execution_module._process_tree_rss(process)


def test_exited_descendant_is_ignored_but_missing_root_is_not() -> None:
    from types import SimpleNamespace

    import psutil

    def disappeared():
        raise psutil.NoSuchProcess(pid=123456)

    process = SimpleNamespace(
        memory_info=lambda: SimpleNamespace(rss=7),
        children=lambda **kwargs: [SimpleNamespace(memory_info=disappeared)],
    )
    assert execution_module._process_tree_rss(process) == 7
    process.memory_info = disappeared
    with pytest.raises(psutil.NoSuchProcess):
        execution_module._process_tree_rss(process)


@pytest.fixture
def sleeping_worker():
    """Real bounded child; the fixture also cleans up if an assertion fails."""
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        yield child
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=2)


@pytest.mark.parametrize("error_kind", ["denied", "missing", "unexpected"])
def test_monitoring_exception_terminates_and_reaps_real_worker(
    monkeypatch, sleeping_worker, error_kind,
) -> None:
    import psutil

    errors = {
        "denied": psutil.AccessDenied(pid=sleeping_worker.pid),
        "missing": psutil.NoSuchProcess(pid=sleeping_worker.pid),
        "unexpected": RuntimeError("synthetic supervision fault"),
    }

    def fail_measurement(process):
        raise errors[error_kind]

    monkeypatch.setattr(execution_module, "_process_tree_rss", fail_measurement)
    expected = RuntimeError if error_kind == "unexpected" else ExecutionBoundaryError
    with pytest.raises(expected) as caught:
        _supervise_process(sleeping_worker, timeout_seconds=2, memory_limit_bytes=1024)
    if error_kind != "unexpected":
        assert caught.value.code == "worker_supervision_failed"
    assert sleeping_worker.returncode is not None
    assert sleeping_worker.poll() is not None


def test_monitor_constructor_failure_still_reaps_real_worker(monkeypatch, sleeping_worker) -> None:
    import psutil

    def denied(pid):
        raise psutil.AccessDenied(pid=pid)

    monkeypatch.setattr(execution_module.psutil, "Process", denied)
    with pytest.raises(ExecutionBoundaryError) as caught:
        _supervise_process(sleeping_worker, timeout_seconds=2, memory_limit_bytes=1024)
    assert caught.value.code == "worker_cleanup_failed"
    assert sleeping_worker.returncode is not None


def test_already_exited_worker_needs_no_monitor(monkeypatch) -> None:
    from types import SimpleNamespace

    def forbidden(pid):
        raise AssertionError("an exited worker must not be inspected")

    monkeypatch.setattr(execution_module.psutil, "Process", forbidden)
    _supervise_process(SimpleNamespace(poll=lambda: 0), timeout_seconds=1, memory_limit_bytes=1)


@pytest.mark.parametrize("fault", ["kill_denied", "survivor"])
def test_tree_cleanup_attempts_root_and_reports_incomplete_cleanup(monkeypatch, fault) -> None:
    from types import SimpleNamespace

    import psutil

    killed = []

    def kill_descendant():
        killed.append("descendant")
        if fault == "kill_denied":
            raise psutil.AccessDenied(pid=123456)

    descendant = SimpleNamespace(kill=kill_descendant)
    process = SimpleNamespace(
        children=lambda **kwargs: [descendant], kill=lambda: killed.append("root"),
    )
    monkeypatch.setattr(
        execution_module.psutil, "wait_procs",
        lambda items, **kwargs: ([], [descendant] if fault == "survivor" else []),
    )
    with pytest.raises(ExecutionBoundaryError) as caught:
        execution_module._terminate_process_tree(process)
    assert caught.value.code == "worker_cleanup_failed"
    assert killed == ["descendant", "root"]


class _OwnedChild:
    """Popen double: never contacts an actual process ID."""

    pid = 123456

    def __init__(self, returncode=None):
        self.returncode = returncode
        self.kill_calls = 0
        self.wait_calls = 0

    def poll(self):
        return self.returncode

    def kill(self):
        self.kill_calls += 1
        self.returncode = -9

    def wait(self, timeout):
        self.wait_calls += 1
        if self.returncode is None:
            raise subprocess.TimeoutExpired("synthetic worker", timeout)
        return self.returncode


def test_worker_owner_cleans_up_when_supervisor_itself_raises(monkeypatch) -> None:
    from types import SimpleNamespace

    child = _OwnedChild()
    workspaces = []

    def spawn(command, **kwargs):
        workspaces.append(kwargs["cwd"])
        return child

    def unexpected(*args, **kwargs):
        raise RuntimeError("synthetic supervisor fault")

    process = SimpleNamespace(children=lambda **kwargs: [], kill=child.kill)
    monkeypatch.setattr(execution_module.subprocess, "Popen", spawn)
    monkeypatch.setattr(execution_module, "_supervise_process", unexpected)
    monkeypatch.setattr(execution_module.psutil, "Process", lambda pid: process)
    monkeypatch.setattr(execution_module.psutil, "wait_procs", lambda *a, **k: ([], []))
    with pytest.raises(RuntimeError, match="synthetic supervisor fault"):
        execution_module._run_worker({"protocol_version": 1})
    assert child.kill_calls > 0
    assert child.wait_calls > 0
    assert len(workspaces) == 1 and not workspaces[0].exists()


def test_cleanup_reaps_child_even_if_direct_kill_fails(monkeypatch) -> None:
    child = _OwnedChild()

    def disappeared(pid):
        raise execution_module.psutil.NoSuchProcess(pid=pid)

    def denied():
        raise PermissionError("synthetic kill denial")

    monkeypatch.setattr(execution_module.psutil, "Process", disappeared)
    child.kill = denied
    with pytest.raises(ExecutionBoundaryError) as caught:
        execution_module._cleanup_worker(child)
    assert caught.value.code == "worker_cleanup_failed"
    assert child.wait_calls == 1


def test_worker_failure_discards_diagnostics_and_removes_workspace(monkeypatch) -> None:
    child = _OwnedChild(returncode=1)
    workspaces = []

    def spawn(command, **kwargs):
        workspaces.append(kwargs["cwd"])
        assert kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["stdout"] == subprocess.DEVNULL
        return child

    monkeypatch.setattr(execution_module.subprocess, "Popen", spawn)
    with pytest.raises(ExecutionBoundaryError) as caught:
        execution_module._run_worker({"protocol_version": 1})
    assert caught.value.code == "worker_failed"
    assert str(caught.value) == "The isolated execution worker failed."
    assert child.wait_calls > 0
    assert not workspaces[0].exists()


@pytest.mark.parametrize("body,status", [
    ('{"workflow":{"value":1e10000}}', 400),
    ('[' * 65 + '0' + ']' * 65, 413),
])
def test_execute_inherits_hardened_json_transport_before_worker(monkeypatch, body, status) -> None:
    def forbidden(payload):
        raise AssertionError("invalid transport must not start a worker")

    monkeypatch.setattr(execution_module, "_run_worker", forbidden)
    response = _client().post(
        "/api/v1/workflows/execute", content=body, headers={"Content-Type": "application/json"},
    )
    assert response.status_code == status
