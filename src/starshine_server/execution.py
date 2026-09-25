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
_MAX_INTERNAL_ERROR_BYTES = 8 * 1024
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
    """Return resident bytes for the worker and any descendants that still exist."""
    processes = [process]
    with suppress(psutil.Error):
        processes.extend(process.children(recursive=True))

    total = 0
    for item in processes:
        with suppress(psutil.Error):
            total += item.memory_info().rss
    return total


def _terminate_process_tree(process: psutil.Process) -> None:
    """Kill descendants before the worker so an execution boundary cannot leave children behind."""
    descendants: list[psutil.Process] = []
    with suppress(psutil.Error):
        descendants = process.children(recursive=True)

    for child in reversed(descendants):
        with suppress(psutil.Error):
            child.kill()
    with suppress(psutil.Error):
        process.kill()
    with suppress(psutil.Error):
        psutil.wait_procs([*descendants, process], timeout=2)


def _supervise_process(
    child: subprocess.Popen[bytes],
    *,
    timeout_seconds: float,
    memory_limit_bytes: int,
) -> None:
    """Wait for a child while enforcing wall-clock and resident-memory boundaries."""
    started = time.monotonic()
    try:
        process = psutil.Process(child.pid)
    except psutil.Error as exc:
        with suppress(Exception):
            child.kill()
        raise ExecutionBoundaryError(
            code="worker_supervision_failed",
            message="The execution worker could not be supervised safely.",
            status_code=500,
        ) from exc

    while child.poll() is None:
        elapsed = time.monotonic() - started
        if elapsed > timeout_seconds:
            _terminate_process_tree(process)
            with suppress(Exception):
                child.wait(timeout=2)
            raise ExecutionBoundaryError(
                code="execution_timeout",
                message="Workflow execution exceeded the service wall-clock limit.",
                status_code=504,
                limit=int(timeout_seconds),
                actual=int(elapsed),
            )

        resident_bytes = _process_tree_rss(process)
        if resident_bytes > memory_limit_bytes:
            _terminate_process_tree(process)
            with suppress(Exception):
                child.wait(timeout=2)
            raise ExecutionBoundaryError(
                code="execution_memory_limit",
                message="Workflow execution exceeded the service resident-memory limit.",
                status_code=422,
                limit=memory_limit_bytes,
                actual=resident_bytes,
            )

        time.sleep(_POLL_SECONDS)


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
        stderr_path = workspace / "worker.stderr"
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

        try:
            with stderr_path.open("wb") as stderr_stream:
                child = subprocess.Popen(
                    command,
                    cwd=workspace,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=stderr_stream,
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
            with suppress(OSError):
                request_path.chmod(stat.S_IWUSR | stat.S_IRUSR)

        if return_code != 0:
            diagnostic = ""
            with suppress(OSError):
                diagnostic = stderr_path.read_text(encoding="utf-8", errors="replace")
            diagnostic = diagnostic[:_MAX_INTERNAL_ERROR_BYTES]
            raise ExecutionBoundaryError(
                code="worker_failed",
                message=(
                    "The isolated execution worker failed."
                    if not diagnostic
                    else "The isolated execution worker failed; details are retained internally."
                ),
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
