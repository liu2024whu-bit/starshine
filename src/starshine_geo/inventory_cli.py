from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import StarshineError
from .inventory import inventory_source, render_source_inventory_markdown


def build_inventory_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="starshine inventory")
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Render machine-readable JSON or review-friendly Markdown",
    )
    parser.add_argument(
        "--force-feature-count",
        action="store_true",
        help="Allow GeoPackage drivers to perform an expensive feature count",
    )
    parser.add_argument(
        "--include-bounds",
        action="store_true",
        help="Include source extents; omitted by default for privacy and cost",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--diagnostic-format",
        choices=("text", "json"),
        default="text",
    )
    return parser


def _print_error(exc: StarshineError, diagnostic_format: str) -> None:
    if diagnostic_format == "json":
        print(
            json.dumps({"error": "starshine_error", "message": str(exc)}, sort_keys=True),
            file=sys.stderr,
        )
    else:
        print(f"starshine: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = build_inventory_parser().parse_args(argv)
    try:
        if args.output is not None and args.output.resolve() == args.source.resolve():
            raise StarshineError("inventory output must not overwrite the source")
        report = inventory_source(
            args.source,
            force_feature_count=args.force_feature_count,
            include_bounds=args.include_bounds,
        )
        content = (
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            if args.format == "json"
            else render_source_inventory_markdown(report)
        )
        if args.output is None:
            print(content, end="")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
            print(args.output)
        return 0
    except StarshineError as exc:
        _print_error(exc, args.diagnostic_format)
        return 2


__all__ = ["build_inventory_parser", "main"]
