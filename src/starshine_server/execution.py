from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import psutil

import starshine_geo

from .limits import (
    MAX_EXECUTION_MEMORY_BYTES,
    MAX_EXECUTION_RESPONSE_BYTES,
    MAX_EXECUTION_SECONDS,
    enforce_inline_preflight_limits,
    execution_limits,
)

_POLL_SECONDS = 0.02
_SENSITIVE_ENV_PARTS = (
    "API_KEY",
    "CREDENTIAL",
    "PASSWORD",
    "PASSWD",
    "PRIVATE_KEY",
    "SECRET",
    "TOKEN",
)


class PreflightRejectedError(Exception):
    """Raised when canonical Core Preflight blocks execution."""

    def __init__(self, report: dict[str, Any]) -> None:
        self.report = report
        super().__init__("Workflow inputs failed Preflight; execution was not started.")


class ExecutionBoundaryError(Exception):
    """Stable service-level execution failure that does not leak workspace details."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        limit: int | None = None,
        actual: int | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.limit = limit
        self.actual = actual
        super().__init__(message)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error": "execution_boundary",
            "code": self.code,
            "message": str(self),
        }
        if self.limit is not None:
            payload["limit"] = self.limit
        if self.actual is not None:
            payload["actual"] = self.actual
        return payload


def _safe_worker_environment() -> dict[str, str]:
    """Drop common credential-bearing environment variables before spawning the worker."""
    safe: dict[str, str] = {}
    for key, value in os.environ.items():
        normalized = key.upper()
        if any(part in normalized for part in _SENSITIVE_ENV_PARTS):
            continue
        safe[key] = value
    safe["PYTHONUTF8"] = "1"
    return safe


def _process_tree_rss(process: psutil.Process) -> int:
    """Count live resident bytes; inability to inspect a live process is not zero."""
    total = process.memory_info().rss
    for descendant in process.children(recursive=True):
        try:
            total += descendant.memory_info().rss
        except psutil.NoSuchProcess:
            # A descendant can exit between enumeration and measurement.
            continue
    return total


def _cleanup_error() -> ExecutionBoundaryError:
    return ExecutionBoundaryError(
        code="worker_cleanup_failed",
        message="The service could not confirm execution worker cleanup.",
        status_code=500,
    )


def _terminate_process_tree(process: psutil.Process) -> None:
    """Attempt all known kills and report incomplete cleanup instead of hiding it."""
    descendants: list[psutil.Process] = []
    failed = False
    try:
        descendants = process.children(recursive=True)
    except psutil.NoSuchProcess:
        return
    except psutil.Error:
        failed = True

    for item in [*reversed(descendants), process]:
        try:
            item.kill()
        except psutil.NoSuchProcess:
            continue
        except psutil.Error:
            failed = True
    try:
        _, alive = psutil.wait_procs([*descendants, process], timeout=2)
        failed = failed or bool(alive)
    except psutil.Error:
        failed = True
    if failed:
        raise _cleanup_error()


def _cleanup_worker(
    child: subprocess.Popen[bytes], process: psutil.Process | None = None,
) -> None:
    """Always fall back to the owned Popen handle and reap, even if Psutil fails."""
    failed = False
    try:
        if process is None:
            try:
                process = psutil.Process(child.pid)
            except psutil.NoSuchProcess:
                pass
        if process is not None:
            _terminate_process_tree(process)
    except (psutil.Error, ExecutionBoundaryError):
        failed = True
    finally:
        # A process-tree inspection error must not skip direct-child cleanup.
        try:
            if child.poll() is None:
                child.kill()
        except OSError:
            failed = True
        finally:
            try:
                child.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                failed = True
    if failed:
        raise _cleanup_error()


def _supervise_process(
    child: subprocess.Popen[bytes],
    *,
    timeout_seconds: float,
    memory_limit_bytes: int,
) -> None:
    """Enforce limits and fail closed when live-process monitoring is unavailable."""
    started = time.monotonic()
    process: psutil.Process | None = None
    try:
        if child.poll() is not None:
            return
        process = psutil.Process(child.pid)
        while child.poll() is None:
            elapsed = time.monotonic() - started
            if elapsed > timeout_seconds:
                raise ExecutionBoundaryError(
                    code="execution_timeout",
                    message="Workflow execution exceeded the service wall-clock limit.",
                    status_code=504,
                    limit=int(timeout_seconds),
                    actual=int(elapsed),
                )

            resident_bytes = _process_tree_rss(process)
            if resident_bytes > memory_limit_bytes:
                raise ExecutionBoundaryError(
                    code="execution_memory_limit",
                    message="Workflow execution exceeded the service resident-memory limit.",
                    status_code=422,
                    limit=memory_limit_bytes,
                    actual=resident_bytes,
                )
            time.sleep(_POLL_SECONDS)
    except psutil.NoSuchProcess:
        # Exiting between poll and inspection is normal only if Popen confirms it.
        if child.poll() is None:
            raise ExecutionBoundaryError(
                code="worker_supervision_failed",
                message="The execution worker could not be supervised safely.",
                status_code=500,
            ) from None
    except psutil.Error as exc:
        raise ExecutionBoundaryError(
            code="worker_supervision_failed",
            message="The execution worker could not be supervised safely.",
            status_code=500,
        ) from exc
    finally:
        if child.poll() is None:
            _cleanup_worker(child, process)


def _write_worker_request(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    path.write_text(encoded, encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def _read_worker_response(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ExecutionBoundaryError(
            code="worker_protocol_error",
            message="The execution worker did not produce a response.",
            status_code=500,
        )

    size = path.stat().st_size
    if size > MAX_EXECUTION_RESPONSE_BYTES:
        raise ExecutionBoundaryError(
            code="execution_output_too_large",
            message="Workflow execution exceeded the serialized response limit.",
            status_code=422,
            limit=MAX_EXECUTION_RESPONSE_BYTES,
            actual=size,
        )

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionBoundaryError(
            code="worker_protocol_error",
            message="The execution worker produced an unreadable response.",
            status_code=500,
        ) from exc
    if not isinstance(value, dict):
        raise ExecutionBoundaryError(
            code="worker_protocol_error",
            message="The execution worker response must be a JSON object.",
            status_code=500,
        )
    return value


def _run_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Run one fixed worker module in a private temporary workspace."""
    with tempfile.TemporaryDirectory(prefix="starshine-exec-") as directory:
        workspace = Path(directory)
        request_path = workspace / "request.json"
        response_path = workspace / "response.json"
        _write_worker_request(request_path, payload)

        command = [
            sys.executable,
            "-I",
            "-m",
            "starshine_server.worker",
            "--request",
            str(request_path),
            "--response",
            str(response_path),
        ]

        child: subprocess.Popen[bytes] | None = None
        try:
            child = subprocess.Popen(
                command,
                cwd=workspace,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                # Do not retain unbounded or unsanitized worker diagnostics.
                stderr=subprocess.DEVNULL,
                env=_safe_worker_environment(),
                shell=False,
            )
            _supervise_process(
                child,
                timeout_seconds=MAX_EXECUTION_SECONDS,
                memory_limit_bytes=MAX_EXECUTION_MEMORY_BYTES,
            )
            return_code = child.wait(timeout=2)
        finally:
            try:
                if child is not None and child.poll() is None:
                    # Also owns cleanup if supervision itself exits unexpectedly.
                    _cleanup_worker(child)
            finally:
                with suppress(OSError):
                    request_path.chmod(stat.S_IWUSR | stat.S_IRUSR)

        if return_code != 0:
            raise ExecutionBoundaryError(
                code="worker_failed",
                message="The isolated execution worker failed.",
                status_code=500,
            )

        return _read_worker_response(response_path)


def execute_inline_workflow(
    workflow: dict[str, Any],
    layers: dict[str, dict[str, Any]],
    *,
    output_layer: str,
) -> dict[str, Any]:
    """Preflight real inputs, then execute the Core in a bounded child process."""
    enforce_inline_preflight_limits(workflow, layers)

    plan = starshine_geo.plan_workflow(workflow, layers.keys())
    if output_layer not in plan["produced_layers"]:
        raise starshine_geo.ValidationError(
            "output_layer must name a layer produced by the Workflow"
        )

    preflight = starshine_geo.preflight_workflow_inputs(workflow, layers)
    if not preflight["valid"]:
        raise PreflightRejectedError(preflight)

    worker_response = _run_worker(
        {
            "protocol_version": 1,
            "workflow": workflow,
            "layers": layers,
            "output_layer": output_layer,
        }
    )

    if worker_response.get("status") == "core_error":
        raise starshine_geo.ValidationError(
            str(worker_response.get("message", "Workflow execution failed validation."))
        )
    if worker_response.get("status") == "output_limit":
        actual = worker_response.get("actual")
        raise ExecutionBoundaryError(
            code="execution_output_too_large",
            message="Workflow execution exceeded the serialized response limit.",
            status_code=422,
            limit=MAX_EXECUTION_RESPONSE_BYTES,
            actual=actual if isinstance(actual, int) else None,
        )
    if worker_response.get("status") != "ok":
        raise ExecutionBoundaryError(
            code="worker_protocol_error",
            message="The execution worker returned an unknown status.",
            status_code=500,
        )

    result = worker_response.get("result")
    manifest = worker_response.get("manifest")
    if not isinstance(result, dict) or not isinstance(manifest, dict):
        raise ExecutionBoundaryError(
            code="worker_protocol_error",
            message="The execution worker omitted result evidence.",
            status_code=500,
        )

    response = {
        "status": "succeeded",
        "output_layer": output_layer,
        "result": result,
        "manifest": manifest,
        "preflight": preflight,
        "execution_policy": execution_limits(),
    }
    encoded = json.dumps(
        response,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_EXECUTION_RESPONSE_BYTES:
        raise ExecutionBoundaryError(
            code="execution_output_too_large",
            message="Workflow execution exceeded the serialized response limit.",
            status_code=422,
            limit=MAX_EXECUTION_RESPONSE_BYTES,
            actual=len(encoded),
        )
    return response


__all__ = [
    "ExecutionBoundaryError",
    "PreflightRejectedError",
    "execute_inline_workflow",
]
