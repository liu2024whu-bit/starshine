"""Experiment-only observation of the existing RSS-error decision poll (#187).

Nothing in src imports this module. No OS function or Popen class is replaced.
The guard deliberately supports only the reviewed CPython/Starshine sources.
"""
from __future__ import annotations

import ast
import errno
import hashlib
import inspect
import json
import os
import platform
import subprocess
import sys
import textwrap
from contextlib import contextmanager
from contextvars import ContextVar
from unittest.mock import patch

import psutil

# Fingerprints ignore line endings/comments/docstrings and empty AST fields added
# across Python versions, not executable changes.
# CPython v3.14.10 Lib/subprocess.py, POSIX Popen._internal_poll.
_POLL_AST_SHA256 = "be2e7dbaebb5429acca00be68f7f7a8a731e970a7397a2c48e55b9dde40ee6c8"
# main 24d61b94172e1a2057da782a27d3ad06da1eb267.
_SUPERVISOR_AST_SHA256 = "a3bd6b3770a99d177150bb8f760ef1fede40c35957d6d8eb28740ed906fbb206"


def _source_fingerprint(source: str) -> str:
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and ast.get_docstring(node) is not None
        ):
            node.body.pop(0)

    def canonical(value):
        if isinstance(value, ast.AST):
            fields = {
                key: canonical(item) for key, item in ast.iter_fields(value)
                if item is not None and not (isinstance(item, list) and not item)
            }
            return [type(value).__name__, fields]
        if isinstance(value, list):
            return [canonical(item) for item in value]
        return value

    encoded = json.dumps(canonical(tree), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _fingerprint(function) -> str:
    return _source_fingerprint(inspect.getsource(function))


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

    The caller must first use require_supported_runtime. Tests can also exercise
    a local POSIX implementation with the same _del_safe private signature.
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
