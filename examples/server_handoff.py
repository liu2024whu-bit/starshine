from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Callable
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_ROOT = Path(__file__).resolve().parent
_WORKFLOW_PATH = _ROOT / "workflow.json"
_LAYER_PATHS = {
    "sites": _ROOT / "data" / "sites.geojson",
    "zones": _ROOT / "data" / "zones.geojson",
}
_OUTPUT_LAYER = "zone_summary"
# Local transport cap, independent of remote claims; not a GIS validation rule.
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class HandoffError(RuntimeError):
    """Raised when the reference HTTP handoff cannot complete safely."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HandoffError(f"Could not read the fixed example {path.name}.") from exc
    if not isinstance(value, dict):
        raise HandoffError(f"Expected a JSON object in {path.name}.")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    body = None
    headers = {"accept": "application/json"}
    if payload is not None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        headers["content-type"] = "application/json"

    try:
        request = Request(url, data=body, headers=headers, method=method)
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        # Proxy/server diagnostics can contain private values. Do not read or echo them.
        exc.close()
        raise HandoffError(f"{method} {path} failed with HTTP {exc.code}.") from None
    except (URLError, OSError, HTTPException, ValueError) as exc:
        raise HandoffError(f"{method} {path} could not complete the HTTP request.") from exc

    if len(raw) > _MAX_RESPONSE_BYTES:
        raise HandoffError(f"{method} {path} exceeded the client response byte limit.")
    try:
        value = json.loads(raw.decode("utf-8"))
        # Reject non-finite values and unpaired surrogates before writing evidence.
        json.dumps(value, allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (ValueError, RecursionError) as exc:
        raise HandoffError(f"{method} {path} returned invalid JSON.") from exc
    if not isinstance(value, dict):
        raise HandoffError(f"{method} {path} returned a non-object JSON response.")
    return value


_RequestJson = Callable[..., dict[str, Any]]


def run_handoff(
    base_url: str,
    output_dir: Path,
    *,
    timeout: float = 15.0,
    request_json: _RequestJson = _request_json,
) -> dict[str, Any]:
    """Run the fixed synthetic reference handoff through the public HTTP API."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise HandoffError("HTTP timeout must be finite and greater than zero.")
    if output_dir.exists() or output_dir.is_symlink():
        raise HandoffError("Choose a new output directory; existing evidence is never overwritten.")
    workflow = _read_json(_WORKFLOW_PATH)
    layers = {name: _read_json(path) for name, path in _LAYER_PATHS.items()}
    layer_names = sorted(layers)

    health = request_json(base_url, "/healthz", timeout=timeout)
    if (health.get("status") != "ok" or health.get("api_version") != 1
            or not isinstance(health.get("core_version"), str) or not health["core_version"]):
        raise HandoffError("The connected service did not report a supported healthy API.")
    limits = request_json(base_url, "/api/v1/limits", timeout=timeout)
    if limits.get("workflow_execution_enabled") is not True:
        raise HandoffError("The connected Starshine Server has workflow execution disabled.")

    execution_policy = limits.get("inline_execution")
    if not isinstance(execution_policy, dict):
        raise HandoffError("The connected Starshine Server did not publish execution limits.")

    review_request = {
        "workflow": workflow,
        "layer_names": layer_names,
    }
    validation = request_json(
        base_url,
        "/api/v1/workflows/validate",
        method="POST",
        payload=review_request,
        timeout=timeout,
    )
    if validation.get("valid") is not True:
        raise HandoffError("Workflow validation did not return a valid result.")

    plan = request_json(
        base_url,
        "/api/v1/workflows/plan",
        method="POST",
        payload=review_request,
        timeout=timeout,
    )
    terminal_layers = plan.get("terminal_layers")
    if not isinstance(terminal_layers, list) or _OUTPUT_LAYER not in terminal_layers:
        raise HandoffError("The reviewed plan does not expose the expected terminal output layer.")

    preflight = request_json(
        base_url,
        "/api/v1/workflows/preflight",
        method="POST",
        payload={"workflow": workflow, "layers": layers},
        timeout=timeout,
    )
    if preflight.get("valid") is not True:
        raise HandoffError("Preflight failed; the reference handoff will not execute the workflow.")

    for key in ("plan_digest", "workflow_digest"):
        if (not isinstance(plan.get(key), str) or not plan[key]
                or preflight.get(key) != plan[key]):
            raise HandoffError("Preflight evidence does not match the reviewed plan.")

    execution = request_json(
        base_url,
        "/api/v1/workflows/execute",
        method="POST",
        payload={
            "workflow": workflow,
            "layers": layers,
            "output_layer": _OUTPUT_LAYER,
        },
        timeout=timeout,
    )
    if execution.get("status") != "succeeded":
        raise HandoffError("Workflow execution did not report success.")
    if execution.get("output_layer") != _OUTPUT_LAYER:
        raise HandoffError("Workflow execution returned an unexpected output layer.")
    if execution.get("preflight") != preflight:
        raise HandoffError("Execution evidence does not match the Preflight report reviewed by the client.")
    if execution.get("execution_policy") != execution_policy:
        raise HandoffError("Execution policy changed between discovery and execution.")

    result = execution.get("result")
    manifest = execution.get("manifest")
    if not isinstance(result, dict) or not isinstance(manifest, dict):
        raise HandoffError("Workflow execution omitted the result or reproducibility manifest.")

    manifest_output = manifest.get("output_layer")
    if (manifest.get("workflow_digest") != plan["workflow_digest"]
            or manifest.get("starshine_version") != health["core_version"]
            or not isinstance(manifest_output, dict)
            or manifest_output.get("name") != _OUTPUT_LAYER
            or not isinstance(manifest_output.get("digest"), str)
            or not manifest_output["digest"]):
        raise HandoffError("The result manifest does not match the reviewed workflow and service.")

    artifacts = {
        "health": "health.json",
        "limits": "limits.json",
        "validation": "validation.json",
        "plan": "plan.json",
        "preflight": "preflight.json",
        "result": "result.geojson",
        "manifest": "manifest.json",
    }
    summary = {
        "handoff_version": 1,
        "status": "succeeded",
        "api_version": health.get("api_version"),
        "core_version": health.get("core_version"),
        "workflow": "workflow.json",
        "input_layers": {
            "sites": "data/sites.geojson",
            "zones": "data/zones.geojson",
        },
        "output_layer": _OUTPUT_LAYER,
        "execution_policy": execution_policy,
        "artifacts": artifacts,
    }
    # Reserve exclusively after HTTP validation too: another run may have created it meanwhile.
    try:
        output_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise HandoffError("Choose a new output directory; existing evidence is never overwritten.") from exc
    except OSError as exc:
        raise HandoffError("Could not create the handoff output directory.") from exc

    reports = (health, limits, validation, plan, preflight, result, manifest)
    try:
        for filename, report in zip(artifacts.values(), reports):
            _write_json(output_dir / filename, report)
        # This completion marker is written only after every evidence file succeeds.
        _write_json(output_dir / "handoff.json", summary)
    except (OSError, ValueError) as exc:
        raise HandoffError("Could not write handoff evidence; the directory is incomplete.") from exc
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run Starshine's fixed synthetic HTTP handoff example and write review/execution evidence."
        )
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Starshine Server base URL (default: http://127.0.0.1:8000).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="New directory for evidence; existing paths are never overwritten.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP timeout in seconds for each request (default: 15).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        summary = run_handoff(args.base_url, args.output_dir, timeout=args.timeout)
    except HandoffError as exc:
        print(f"Reference handoff failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Reference handoff succeeded: "
        f"{summary['output_layer']} with Starshine Geo {summary['core_version']}."
    )
    print(f"Evidence written to {args.output_dir.resolve()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
