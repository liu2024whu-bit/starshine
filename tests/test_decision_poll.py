from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
from contextlib import nullcontext
from types import MethodType, SimpleNamespace

import pytest

psutil = pytest.importorskip("psutil")
pytest.importorskip("fastapi")

from scripts import decision_poll as diagnostic
from starshine_server import execution

SECRET = "private diagnostic text must not escape"
POSIX = pytest.mark.skipif(os.name != "posix", reason="actual CPython POSIX implementation")


@pytest.mark.parametrize("outcome,path", [
    ((0, 0), "zero"), ((123, 7 << 8), "terminal"), ((456, 0), "unexpected_child"),
    (OSError(errno.ECHILD, SECRET), "error_no_child"),
    (OSError(errno.EINTR, SECRET), "error_interrupted"),
    (OSError(errno.EINVAL, SECRET), "error_invalid"),
    (OSError(errno.EPERM, SECRET), "error_other"),
    (RuntimeError(SECRET), "non_os_error"),
])
def test_waitpid_proxy_preserves_result_exception_arguments_and_call_count(outcome, path):
    calls = []

    def waitpid(*args, **kwargs):
        calls.append((args, kwargs))
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    sentinel = object()
    delegate = SimpleNamespace(waitpid=waitpid, WNOHANG=sentinel)
    observer = diagnostic._WaitpidObservation(delegate, 123)
    assert observer.WNOHANG is sentinel
    if isinstance(outcome, BaseException):
        with pytest.raises(type(outcome)) as caught:
            observer.waitpid(123, sentinel)
        assert caught.value is outcome
    else:
        assert observer.waitpid(123, sentinel) is outcome
    assert calls == [((123, sentinel), {})]
    assert observer.calls == 1 and observer.path == path
    assert SECRET not in json.dumps({"path": observer.path, "calls": observer.calls})


def child_double(events, outcome, *, mode="normal", returncode=None):
    """Use the runtime's original POSIX method; never wait on a real/synthetic PID."""
    child = SimpleNamespace(pid=123, returncode=returncode)

    def acquire(blocking):
        events.append(("acquire", blocking))
        if mode == "skipped":
            return False
        if mode == "raced":
            child.returncode = 7
        return True

    child._waitpid_lock = SimpleNamespace(
        acquire=acquire, release=lambda: events.append(("release",)),
    )

    def waitpid(*args):
        events.append(("waitpid", args))
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    delegate = SimpleNamespace(waitpid=waitpid, WNOHANG=os.WNOHANG, ECHILD=errno.ECHILD)

    def handle_status(status):
        events.append(("status", status))
        child.returncode = os.waitstatus_to_exitcode(status)

    child._handle_exitstatus = handle_status

    def internal(self, _deadstate=None, _del_safe=delegate):
        return subprocess.Popen._internal_poll(self, _deadstate, _del_safe)

    child._internal_poll = MethodType(internal, child)
    child.poll = lambda: child._internal_poll()
    return child


@POSIX
@pytest.mark.parametrize("mode,code,outcome,path,result_kind", [
    ("normal", None, (0, 0), "zero", "none"),
    ("skipped", None, (0, 0), "skipped_lock", "none"),
    ("normal", 7, (0, 0), "terminal", "terminal"),
    ("raced", None, (0, 0), "terminal", "terminal"),
    ("normal", None, (123, 0), "terminal", "terminal"),
    ("normal", None, (123, 7 << 8), "terminal", "terminal"),
    ("normal", None, (123, 9), "terminal", "terminal"),
    ("normal", None, OSError(errno.ECHILD, SECRET), "error_no_child", "terminal"),
    ("normal", None, OSError(errno.EINTR, SECRET), "error_interrupted", "none"),
    ("normal", None, OSError(errno.EINVAL, SECRET), "error_invalid", "none"),
    ("normal", None, OSError(errno.EPERM, SECRET), "error_other", "none"),
    ("normal", None, RuntimeError(SECRET), "non_os_error", "raised"),
])
def test_actual_internal_poll_matches_unobserved_control(
    mode, code, outcome, path, result_kind,
):
    traces = []
    outcomes = []
    observations = []
    for observed in (False, True):
        events = []
        child = child_double(events, outcome, mode=mode, returncode=code)
        original = child._internal_poll
        if observed:
            diagnostic._arm_next_poll(child, observations)
        try:
            value = child.poll()
        except RuntimeError as exc:
            assert exc is outcome
            value = exc
        outcomes.append((value, child.returncode))
        traces.append(events)
        assert child._internal_poll is original
    assert traces[0] == traces[1]
    assert outcomes[0] == outcomes[1]
    assert observations == [{
        "poll_path": path, "poll_result": result_kind,
        "waitpid_calls": sum(event[0] == "waitpid" for event in traces[0]),
    }]
    assert SECRET not in json.dumps(observations)


@POSIX
def test_deadstate_and_explicit_delegate_are_preserved():
    child = child_double([], (0, 0))
    observations = []
    deadstate = object()
    error = OSError(errno.EPERM, SECRET)
    calls = []

    def waitpid(*args):
        calls.append(args)
        raise error

    delegate = SimpleNamespace(waitpid=waitpid, WNOHANG=456, ECHILD=errno.ECHILD)
    diagnostic._arm_next_poll(child, observations)
    assert child._internal_poll(deadstate, delegate) is deadstate
    assert child.returncode is deadstate
    assert calls == [(123, 456)]
    assert observations == [{
        "poll_path": "error_other", "poll_result": "terminal", "waitpid_calls": 1,
    }]


@POSIX
@pytest.mark.parametrize("decision", ["zero", "skipped", "echild", "eintr", "terminal"])
@pytest.mark.parametrize("cleanup_failed", [False, True])
def test_supervision_and_cleanup_order_matches_unobserved_control(
    monkeypatch, decision, cleanup_failed,
):
    traces, results, observations = [], [], []

    def run(observed):
        events = []
        stage = {"rss_failed": False, "decision_done": False}
        child = child_double(events, (0, 0))

        def waitpid(*args):
            events.append(("waitpid", args))
            if stage["rss_failed"] and not stage["decision_done"]:
                stage["decision_done"] = True
                if decision == "terminal":
                    return (123, 7 << 8)
                if decision in {"eintr", "echild"}:
                    raise OSError(errno.EINTR if decision == "eintr" else errno.ECHILD, SECRET)
            return (0, 0)

        def acquire(blocking):
            events.append(("acquire", blocking))
            if stage["rss_failed"] and not stage["decision_done"] and decision == "skipped":
                stage["decision_done"] = True
                return False
            return True

        child._waitpid_lock.acquire = acquire
        delegate = SimpleNamespace(waitpid=waitpid, WNOHANG=os.WNOHANG, ECHILD=errno.ECHILD)

        def internal(self, _deadstate=None, _del_safe=delegate):
            events.append(("internal",))
            return subprocess.Popen._internal_poll(self, _deadstate, _del_safe)

        child._internal_poll = MethodType(internal, child)
        original_internal = child._internal_poll

        def measure():
            events.append(("rss",))
            stage["rss_failed"] = True
            raise psutil.NoSuchProcess(123, SECRET)

        def kill():
            events.append(("kill",))
            child.returncode = -9

        def wait(timeout):
            events.append(("wait", timeout))
            return child.returncode

        child.kill, child.wait = kill, wait
        process = SimpleNamespace(
            memory_info=measure,
            children=lambda **kwargs: events.append(("children", kwargs)) or [],
            kill=kill,
        )

        def lookup(pid):
            events.append(("lookup", pid))
            return process

        def wait_procs(items, timeout):
            events.append(("wait_procs", timeout))
            return ([], [process] if cleanup_failed else [])

        with monkeypatch.context() as scoped:
            scoped.setattr(execution.psutil, "Process", lookup)
            scoped.setattr(execution.psutil, "wait_procs", wait_procs)
            context = diagnostic.observe_supervision(execution, observations) if observed else (
                nullcontext()
            )
            with context:
                try:
                    value = execution._supervise_process(
                        child, timeout_seconds=10, memory_limit_bytes=512 * 1024 * 1024,
                    )
                except execution.ExecutionBoundaryError as exc:
                    value = exc.as_dict()
        assert child._internal_poll is original_internal
        traces.append(events)
        results.append((value, child.returncode))

    run(False)
    run(True)
    assert traces[0] == traces[1]
    assert results[0] == results[1]
    expected = {
        "zero": ("zero", "none", 1), "skipped": ("skipped_lock", "none", 0),
        "echild": ("error_no_child", "terminal", 1),
        "eintr": ("error_interrupted", "none", 1), "terminal": ("terminal", "terminal", 1),
    }[decision]
    assert observations == [dict(zip(("poll_path", "poll_result", "waitpid_calls"), expected))]


def test_guard_refuses_other_runtime_before_patching(monkeypatch):
    original = execution._supervise_process
    monkeypatch.setattr(diagnostic.platform, "python_implementation", lambda: "unsupported")
    with pytest.raises(RuntimeError, match="^unsupported_poll_observation_runtime$"):
        diagnostic.require_supported_runtime(execution)
    assert execution._supervise_process is original


def test_source_guard_ignores_docstrings_and_indentation_but_not_code():
    original = 'def poll():\n    """first docs"""\n    return None\n'
    reformatted = '    def poll():\n        """other docs"""\n        return None\n'
    assert diagnostic._source_fingerprint(original) == diagnostic._source_fingerprint(reformatted)
    assert diagnostic._source_fingerprint(original) != diagnostic._source_fingerprint(
        original.replace("return None", "return 0")
    )


@POSIX
@pytest.mark.parametrize("terminal", [False, True])
@pytest.mark.parametrize("error_type", [
    psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied, psutil.Error,
])
def test_real_worker_is_still_reaped_or_confirmed_terminal(monkeypatch, terminal, error_type):
    child = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.readline()"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    original_class_poll = subprocess.Popen._internal_poll
    observations = []

    def fail_measurement(process):
        if terminal:
            child.stdin.close()
            assert child.wait(timeout=2) == 0
        raise error_type(SECRET) if error_type is psutil.Error else error_type(child.pid)

    monkeypatch.setattr(execution, "_process_tree_rss", fail_measurement)
    try:
        with diagnostic.observe_supervision(execution, observations):
            if terminal:
                execution._supervise_process(child, timeout_seconds=10, memory_limit_bytes=1)
            else:
                with pytest.raises(execution.ExecutionBoundaryError) as caught:
                    execution._supervise_process(child, timeout_seconds=10, memory_limit_bytes=1)
                assert caught.value.code == "worker_supervision_failed"
        assert child.returncode is not None
        assert "_internal_poll" not in vars(child)
        assert subprocess.Popen._internal_poll is original_class_poll
        assert observations == [{
            "poll_path": "terminal" if terminal else "zero",
            "poll_result": "terminal" if terminal else "none",
            "waitpid_calls": 0 if terminal else 1,
        }]
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=2)
        child.stdin.close()


@POSIX
def test_precise_source_guard_for_experiment(monkeypatch):
    monkeypatch.setattr(diagnostic.sys, "version_info", (3, 14, 10))
    monkeypatch.setattr(diagnostic.platform, "python_implementation", lambda: "CPython")
    # Fingerprint differences are refused, never silently treated as equivalent.
    monkeypatch.setattr(diagnostic, "_POLL_AST_SHA256", "unreviewed")
    with pytest.raises(RuntimeError, match="^unsupported_poll_observation_source$"):
        diagnostic.require_supported_runtime(execution)


@POSIX
def test_experiment_source_fingerprint_matches_on_exact_cpython():
    if sys.version_info[:3] != (3, 14, 10):
        pytest.skip("strict experiment guard requires exact 3.14.10")
    diagnostic.require_supported_runtime(execution)
