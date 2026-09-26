from __future__ import annotations

import argparse
import json
from collections.abc import Callable
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


class HandoffError(RuntimeError):
    """Raised when the reference HTTP handoff cannot complete safely."""


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise HandoffError(f"Expected a JSON object in {path.name}.")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
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

    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise HandoffError(
            f"{method} {path} failed with HTTP {exc.code}: {detail}"
        ) from None
    except URLError as exc:
        raise HandoffError(f"{method} {path} could not reach the Starshine Server.") from exc

    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
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
    workflow = _read_json(_WORKFLOW_PATH)
    layers = {name: _read_json(path) for name, path in _LAYER_PATHS.items()}
    layer_names = sorted(layers)

    health = request_json(base_url, "/healthz", timeout=timeout)
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

    artifacts = {
        "health": "health.json",
        "limits": "limits.json",
        "validation": "validation.json",
        "plan": "plan.json",
        "preflight": "preflight.json",
        "result": "result.geojson",
        "manifest": "manifest.json",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / artifacts["health"], health)
    _write_json(output_dir / artifacts["limits"], limits)
    _write_json(output_dir / artifacts["validation"], validation)
    _write_json(output_dir / artifacts["plan"], plan)
    _write_json(output_dir / artifacts["preflight"], preflight)
    _write_json(output_dir / artifacts["result"], result)
    _write_json(output_dir / artifacts["manifest"], manifest)

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
    _write_json(output_dir / "handoff.json", summary)
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
        help="Directory that will receive the handoff evidence files.",
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
    summary = run_handoff(
        args.base_url,
        args.output_dir,
        timeout=args.timeout,
    )
    print(
        "Reference handoff succeeded: "
        f"{summary['output_layer']} with Starshine Geo {summary['core_version']}."
    )
    print(f"Evidence written to {args.output_dir.resolve()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
