"""Experiment-only observation of the existing RSS-error decision poll (#187).

Nothing in src imports this module. No OS function or Popen class is replaced.
The guard deliberately supports only the reviewed CPython/Starshine sources.
"""
from __future__ import annotations

import ast
import errno
import hashlib
import inspect
import os
import platform
import subprocess
import sys
import textwrap
from contextlib import contextmanager
from contextvars import ContextVar
from unittest.mock import patch

import psutil

# AST fingerprints ignore checkout line endings/comments, not executable changes.
# CPython v3.14.10 Lib/subprocess.py, POSIX Popen._internal_poll.
_POLL_AST_SHA256 = "727465c4b6954b50a8bb31e245cf243a431f66f540372e0754ab173bbe90298b"
# main 24d61b94172e1a2057da782a27d3ad06da1eb267.
_SUPERVISOR_AST_SHA256 = "8f4757807cbfe3a626aa0b93ceff4f09874b546206fc9eb4c3803edb1f9716b6"


def _fingerprint(function) -> str:
    source = textwrap.dedent(inspect.getsource(function))
    tree = ast.dump(ast.parse(source), include_attributes=False)
    return hashlib.sha256(tree.encode("utf-8")).hexdigest()


def require_supported_runtime(execution) -> None:
    """Refuse an unreviewed private implementation before any worker is started."""
    if (
        platform.python_implementation() != "CPython"
        or sys.version_info[:3] != (3, 14, 10)
        or os.name != "posix"
    ):
        raise RuntimeError("unsupported_poll_observation_runtime")
    method = subprocess.Popen._internal_poll
    parameters = tuple(inspect.signature(method).parameters)
    if parameters != ("self", "_deadstate", "_del_safe"):
        raise RuntimeError("unsupported_poll_observation_signature")
    if (
        _fingerprint(method) != _POLL_AST_SHA256
        or _fingerprint(execution._supervise_process) != _SUPERVISOR_AST_SHA256
    ):
        raise RuntimeError("unsupported_poll_observation_source")


class _WaitpidObservation:
    """Delegate the captured _del_safe object; retain only fixed categories."""

    def __init__(self, delegate, owned_pid):
        self.delegate = delegate
        self.owned_pid = owned_pid
        self.calls = 0
        self.path = "not_called"

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def waitpid(self, *args, **kwargs):
        self.calls += 1
        try:
            result = self.delegate.waitpid(*args, **kwargs)
        except OSError as exc:
            self.path = {
                errno.ECHILD: "error_no_child",
                errno.EINTR: "error_interrupted",
                errno.EINVAL: "error_invalid",
            }.get(exc.errno, "error_other")
            raise
        except BaseException:
            self.path = "non_os_error"
            raise
        self.path = (
            "zero" if result[0] == 0 else
            "terminal" if result[0] == self.owned_pid else "unexpected_child"
        )
        return result


def _arm_next_poll(child, observations: list[dict]) -> object:
    """Observe one already-required poll, restoring the instance before its call."""
    original = child._internal_poll
    default_delegate = inspect.signature(original).parameters["_del_safe"].default
    absent = object()
    previous = vars(child).get("_internal_poll", absent)

    def restore():
        if previous is absent:
            vars(child).pop("_internal_poll", None)
        else:
            child._internal_poll = previous

    def observed(_deadstate=None, _del_safe=default_delegate):
        restore()
        observer = _WaitpidObservation(_del_safe, child.pid)
        result_kind = "raised"
        try:
            result = original(_deadstate, _del_safe=observer)
            result_kind = "none" if result is None else "terminal"
            return result
        finally:
            path = observer.path
            if path == "not_called":
                path = "skipped_lock" if result_kind == "none" else result_kind
            observations.append({
                "poll_path": path,
                "poll_result": result_kind,
                "waitpid_calls": observer.calls,
            })

    child._internal_poll = observed
    return restore


@contextmanager
def observe_supervision(execution, observations: list[dict]):
    """Scope hooks to a serial diagnostic harness, never a deployed Server.

    The caller must first use require_supported_runtime. Tests also exercise the
    unchanged local POSIX implementation on the other supported Python versions.
    Only an RSS Psutil error arms the next poll in the guarded supervisor's except
    branch. Initial/loop/finally/cleanup polls remain the original bound method.
    """
    original_supervise = execution._supervise_process
    original_rss = execution._process_tree_rss
    active = ContextVar("diagnostic_owned_child", default=None)

    def supervise(child, **kwargs):
        state = {"child": child, "restore": None}
        token = active.set(state)
        try:
            return original_supervise(child, **kwargs)
        finally:
            if state["restore"] is not None:
                state["restore"]()
            active.reset(token)

    def rss(process):
        try:
            return original_rss(process)
        except psutil.Error:
            state = active.get()
            if state is not None:
                state["restore"] = _arm_next_poll(state["child"], observations)
            raise

    with patch.object(execution, "_supervise_process", supervise), patch.object(
        execution, "_process_tree_rss", rss,
    ):
        yield
