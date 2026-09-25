from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import starshine_geo

from .limits import MAX_EXECUTION_RESPONSE_BYTES


def _load_request(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("protocol_version") != 1:
        raise ValueError("unsupported worker request protocol")
    return value


def _serialize_response(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _write_response(path: Path, value: dict[str, Any]) -> None:
    encoded = _serialize_response(value)
    if len(encoded) > MAX_EXECUTION_RESPONSE_BYTES:
        encoded = _serialize_response(
            {
                "status": "output_limit",
                "actual": len(encoded),
            }
        )

    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(encoded)
    temporary.replace(path)


def _execute(request: dict[str, Any]) -> dict[str, Any]:
    workflow = request.get("workflow")
    layers = request.get("layers")
    output_layer = request.get("output_layer")
    if not isinstance(workflow, dict) or not isinstance(layers, dict):
        raise ValueError("worker request is missing Workflow inputs")
    if not isinstance(output_layer, str) or not output_layer:
        raise ValueError("worker request is missing output_layer")

    context = starshine_geo.run_workflow(workflow, layers)
    if output_layer not in context:
        raise starshine_geo.ValidationError(
            "output_layer was not produced by Workflow execution"
        )

    result = context[output_layer]
    manifest = starshine_geo.build_manifest(
        workflow,
        layers,
        output_layer_name=output_layer,
        output_layer=result,
    )
    return {
        "status": "ok",
        "result": result,
        "manifest": manifest,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        request = _load_request(args.request)
        response = _execute(request)
    except starshine_geo.StarshineError as exc:
        response = {
            "status": "core_error",
            "message": str(exc),
        }
    except Exception:
        return 1

    _write_response(args.response, response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
