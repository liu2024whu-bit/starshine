from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ._version import __version__
from .errors import StarshineError, WorkflowValidationError
from .explain import explain_workflow, render_workflow_explanation_markdown
from .graph import build_workflow_graph, render_workflow_mermaid
from .inspection import inspect_feature_collection
from .io import read_json, write_json
from .manifest import build_manifest
from .operator_registry import operator_catalog
from .planning import plan_workflow
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
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
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

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Validate and summarize one GeoJSON FeatureCollection",
    )
    inspect_parser.add_argument("source", type=Path)
    inspect_parser.add_argument(
        "--output",
        type=Path,
        help="Optionally write the inspection report instead of printing it",
    )
    _add_diagnostic_format(inspect_parser)

    operators_parser = subparsers.add_parser(
        "operators",
        help="Print the machine-readable catalog of bounded workflow operators",
    )
    operators_parser.add_argument(
        "--output",
        type=Path,
        help="Optionally write the operator catalog instead of printing it",
    )

    plan_parser = subparsers.add_parser(
        "plan",
        help="Validate and describe workflow dependencies without reading feature data",
    )
    plan_parser.add_argument("workflow", type=Path)
    plan_parser.add_argument(
        "--layer-name",
        action="append",
        default=[],
        metavar="NAME",
        help="Declare an available external layer name; repeat for multiple layers",
    )
    plan_parser.add_argument(
        "--output",
        type=Path,
        help="Optionally write the workflow plan instead of printing it",
    )
    _add_diagnostic_format(plan_parser)

    graph_parser = subparsers.add_parser(
        "graph",
        help="Render a validated data-free workflow graph as JSON or Mermaid",
    )
    graph_parser.add_argument("workflow", type=Path)
    graph_parser.add_argument(
        "--layer-name",
        action="append",
        default=[],
        metavar="NAME",
        help="Declare an available external layer name; repeat for multiple layers",
    )
    graph_parser.add_argument(
        "--format",
        choices=("json", "mermaid"),
        default="mermaid",
        help="Choose a machine-readable JSON graph or Mermaid flowchart text",
    )
    graph_parser.add_argument(
        "--output",
        type=Path,
        help="Optionally write the workflow graph instead of printing it",
    )
    _add_diagnostic_format(graph_parser)

    explain_parser = subparsers.add_parser(
        "explain",
        help="Explain a validated data-free workflow as JSON or Markdown",
    )
    explain_parser.add_argument("workflow", type=Path)
    explain_parser.add_argument(
        "--layer-name",
        action="append",
        default=[],
        metavar="NAME",
        help="Declare an available external layer name; repeat for multiple layers",
    )
    explain_parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Choose a machine-readable JSON report or Markdown explanation",
    )
    explain_parser.add_argument(
        "--output",
        type=Path,
        help="Optionally write the workflow explanation instead of printing it",
    )
    _add_diagnostic_format(explain_parser)
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


def _inspect_command(args: argparse.Namespace) -> int:
    if args.output is not None and args.output.resolve() == args.source.resolve():
        raise StarshineError("inspection output must not overwrite the source GeoJSON")
    report = inspect_feature_collection(read_json(args.source))
    if args.output is None:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        write_json(report, args.output)
        print(args.output)
    return 0


def _operators_command(args: argparse.Namespace) -> int:
    catalog = operator_catalog()
    if args.output is None:
        print(json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        write_json(catalog, args.output)
        print(args.output)
    return 0


def _plan_command(args: argparse.Namespace) -> int:
    if args.output is not None and args.output.resolve() == args.workflow.resolve():
        raise StarshineError("workflow plan output must not overwrite the workflow file")
    workflow = read_json(args.workflow)
    plan = plan_workflow(workflow, _parse_layer_names(args.layer_name))
    if args.output is None:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        write_json(plan, args.output)
        print(args.output)
    return 0


def _graph_command(args: argparse.Namespace) -> int:
    if args.output is not None and args.output.resolve() == args.workflow.resolve():
        raise StarshineError("workflow graph output must not overwrite the workflow file")
    workflow = read_json(args.workflow)
    graph = build_workflow_graph(workflow, _parse_layer_names(args.layer_name))
    if args.format == "json":
        content = json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        content = render_workflow_mermaid(graph)

    if args.output is None:
        print(content, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(args.output)
    return 0


def _explain_command(args: argparse.Namespace) -> int:
    if args.output is not None and args.output.resolve() == args.workflow.resolve():
        raise StarshineError("workflow explanation output must not overwrite the workflow file")
    workflow = read_json(args.workflow)
    explanation = explain_workflow(workflow, _parse_layer_names(args.layer_name))
    if args.format == "json":
        content = json.dumps(explanation, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        content = render_workflow_explanation_markdown(explanation)

    if args.output is None:
        print(content, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(args.output)
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
        if args.command == "inspect":
            return _inspect_command(args)
        if args.command == "operators":
            return _operators_command(args)
        if args.command == "plan":
            return _plan_command(args)
        if args.command == "graph":
            return _graph_command(args)
        if args.command == "explain":
            return _explain_command(args)
        return _run_command(args)
    except StarshineError as exc:
        _print_error(exc, getattr(args, "diagnostic_format", "text"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
