from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import StarshineError
from .io import read_json, write_json
from .workflow import run_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="starshine")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run a bounded JSON spatial workflow")
    run_parser.add_argument("workflow", type=Path)
    run_parser.add_argument("--layer", action="append", default=[], metavar="NAME=PATH")
    run_parser.add_argument("--output-layer", required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    return parser


def _parse_layers(values: list[str]) -> dict[str, dict]:
    layers = {}
    for value in values:
        if "=" not in value:
            raise StarshineError("--layer must use NAME=PATH")
        name, path = value.split("=", 1)
        if not name.strip() or name in layers:
            raise StarshineError(f"invalid or duplicate layer name: {name!r}")
        layers[name] = read_json(path)
    return layers


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        layers = _parse_layers(args.layer)
        results = run_workflow(read_json(args.workflow), layers)
        if args.output_layer not in results:
            raise StarshineError(f"workflow did not produce layer: {args.output_layer}")
        write_json(results[args.output_layer], args.output)
    except StarshineError as exc:
        print(f"starshine: {exc}", file=sys.stderr)
        return 2
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
