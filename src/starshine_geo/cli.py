from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import StarshineError, WorkflowValidationError
from .io import read_json, write_json
from .manifest import build_manifest
from .workflow import run_workflow, validate_workflow


def _add_diagnostic_format(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--diagnostic-format",
        choices=("text", "json"),
        default="text",
        help="Render validation failures as text or a stable JSON envelope",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="starshine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a bounded JSON spatial workflow")
    run_parser.add_argument("workflow", type=Path)
    run_parser.add_argument("--layer", action="append", default=[], metavar="NAME=PATH")
    run_parser.add_argument("--output-layer", required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument(
        "--manifest",
        type=Path,
        help="Optionally write a path-free reproducibility manifest",
    )
    _add_diagnostic_format(run_parser)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate workflow structure and parameters without executing operators",
    )
    validate_parser.add_argument("workflow", type=Path)
    validate_parser.add_argument(
        "--layer-name",
        action="append",
        default=[],
        metavar="NAME",
        help="Declare an available in-memory layer name; repeat for multiple layers",
    )
    _add_diagnostic_format(validate_parser)
    return parser


def _parse_layers(values: list[str]) -> dict[str, dict]:
    layers = {}
    for value in values:
        if "=" not in value:
            raise StarshineError("--layer must use NAME=PATH")
        name, path = value.split("=", 1)
        name = name.strip()
        if not name or name in layers:
            raise StarshineError(f"invalid or duplicate layer name: {name!r}")
        layers[name] = read_json(path)
    return layers


def _parse_layer_names(values: list[str]) -> set[str]:
    names: set[str] = set()
    for value in values:
        name = value.strip()
        if not name or name in names:
            raise StarshineError(f"invalid or duplicate layer name: {name!r}")
        names.add(name)
    return names


def _print_error(exc: StarshineError, diagnostic_format: str) -> None:
    if diagnostic_format == "json":
        if isinstance(exc, WorkflowValidationError):
            envelope = {
                "error": "workflow_validation",
                "diagnostic": exc.diagnostic.as_dict(),
            }
        else:
            envelope = {
                "error": "starshine_error",
                "message": str(exc),
            }
        print(json.dumps(envelope, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return
    print(f"starshine: {exc}", file=sys.stderr)


def _validate_command(args: argparse.Namespace) -> int:
    workflow = read_json(args.workflow)
    validate_workflow(workflow, _parse_layer_names(args.layer_name))
    if args.diagnostic_format == "json":
        print(
            json.dumps(
                {"valid": True, "workflow_version": workflow.get("version")},
                sort_keys=True,
            )
        )
    else:
        print("valid")
    return 0


def _run_command(args: argparse.Namespace) -> int:
    workflow = read_json(args.workflow)
    layers = _parse_layers(args.layer)
    results = run_workflow(workflow, layers)
    if args.output_layer not in results:
        raise StarshineError(f"workflow did not produce layer: {args.output_layer}")
    output_layer = results[args.output_layer]
    write_json(output_layer, args.output)
    if args.manifest is not None:
        manifest = build_manifest(
            workflow,
            layers,
            output_layer_name=args.output_layer,
            output_layer=output_layer,
        )
        write_json(manifest, args.manifest)
    print(args.output)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            return _validate_command(args)
        return _run_command(args)
    except StarshineError as exc:
        _print_error(exc, args.diagnostic_format)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
