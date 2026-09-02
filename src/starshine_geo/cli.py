from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ._cli_layer_sources import prepare_layer_bindings
from ._cli_run_output import prepare_run_output
from ._version import __version__
from .contracts import build_workflow_contract, render_workflow_contract_markdown
from .doctor import build_doctor_report, render_doctor_text
from .errors import StarshineError, WorkflowValidationError
from .explain import explain_workflow, render_workflow_explanation_markdown
from .geometry_quality import assess_geometry_quality, render_geometry_quality_markdown
from .graph import build_workflow_graph, render_workflow_mermaid
from .inspection import inspect_feature_collection
from .inventory import inventory_source, render_source_inventory_markdown
from .io import read_json, write_json
from .manifest import build_manifest
from .operator_registry import operator_catalog
from .planning import plan_workflow
from .preflight import preflight_workflow_inputs, render_workflow_preflight_markdown
from .preflight_sarif import build_workflow_preflight_sarif
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

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Check the installed spatial runtime and a deterministic workflow self-test",
    )
    doctor_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Render a human-readable summary or machine-readable JSON report",
    )
    doctor_parser.add_argument(
        "--require-geopackage",
        action="store_true",
        help="Fail when the optional GeoPackage backend is unavailable or its round trip fails",
    )
    doctor_parser.add_argument(
        "--output",
        type=Path,
        help="Optionally write the doctor report instead of printing it",
    )

    run_parser = subparsers.add_parser("run", help="Run a bounded JSON spatial workflow")
    run_parser.add_argument("workflow", type=Path)
    run_parser.add_argument(
        "--layer",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="Bind one workflow layer to a GeoJSON file; repeat for multiple inputs",
    )
    run_parser.add_argument(
        "--geopackage-layer",
        "--gpkg-layer",
        action="append",
        nargs=3,
        default=[],
        metavar=("NAME", "PATH", "LAYER"),
        help=(
            "Bind one workflow layer to an explicitly selected GeoPackage vector layer; "
            "repeat for multiple inputs"
        ),
    )
    run_parser.add_argument("--output-layer", required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument(
        "--output-format",
        choices=("geojson", "geopackage"),
        default="geojson",
        help="Write the selected workflow result as GeoJSON or GeoPackage",
    )
    run_parser.add_argument(
        "--geopackage-output-layer",
        metavar="LAYER",
        help="Explicit GeoPackage destination layer name; requires --output-format geopackage",
    )
    run_parser.add_argument(
        "--overwrite-output",
        action="store_true",
        help="Replace an existing GeoPackage destination; never overwrites workflow inputs",
    )
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

    inventory_parser = subparsers.add_parser(
        "inventory",
        help="Inventory GeoJSON or GeoPackage metadata without attribute values",
    )
    inventory_parser.add_argument("source", type=Path)
    inventory_parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Render machine-readable JSON or review-friendly Markdown",
    )
    inventory_parser.add_argument(
        "--force-feature-count",
        action="store_true",
        help="Allow GeoPackage drivers to perform an expensive feature count",
    )
    inventory_parser.add_argument(
        "--include-bounds",
        action="store_true",
        help="Include source extents; omitted by default for privacy and cost",
    )
    inventory_parser.add_argument(
        "--output",
        type=Path,
        help="Optionally write the inventory report instead of printing it",
    )
    _add_diagnostic_format(inventory_parser)

    quality_parser = subparsers.add_parser(
        "quality",
        help="Assess GeoJSON geometry quality without repairing or transforming data",
    )
    quality_parser.add_argument("source", type=Path)
    quality_parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Choose a machine-readable JSON report or Markdown summary",
    )
    quality_parser.add_argument(
        "--output",
        type=Path,
        help="Optionally write the geometry-quality report instead of printing it",
    )
    _add_diagnostic_format(quality_parser)

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

    contract_parser = subparsers.add_parser(
        "contract",
        help="Describe external layer geometry, CRS, and field requirements",
    )
    contract_parser.add_argument("workflow", type=Path)
    contract_parser.add_argument(
        "--layer-name",
        action="append",
        default=[],
        metavar="NAME",
        help="Declare an available external layer name; repeat for multiple layers",
    )
    contract_parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Choose a machine-readable JSON report or Markdown preparation checklist",
    )
    contract_parser.add_argument(
        "--output",
        type=Path,
        help="Optionally write the workflow input contract instead of printing it",
    )
    _add_diagnostic_format(contract_parser)

    preflight_parser = subparsers.add_parser(
        "preflight",
        help="Check GeoJSON or selected GeoPackage inputs against workflow contracts",
    )
    preflight_parser.add_argument("workflow", type=Path)
    preflight_parser.add_argument(
        "--layer",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="Bind one workflow layer to a GeoJSON file; repeat for multiple inputs",
    )
    preflight_parser.add_argument(
        "--geopackage-layer",
        "--gpkg-layer",
        action="append",
        nargs=3,
        default=[],
        metavar=("NAME", "PATH", "LAYER"),
        help=(
            "Bind one workflow layer to an explicitly selected GeoPackage vector layer; "
            "repeat for multiple inputs"
        ),
    )
    preflight_parser.add_argument(
        "--format",
        choices=("json", "markdown", "sarif"),
        default="markdown",
        help="Choose JSON, Markdown, or GitHub-compatible SARIF output",
    )
    preflight_parser.add_argument(
        "--output",
        type=Path,
        help="Optionally write the workflow preflight report instead of printing it",
    )
    preflight_parser.add_argument(
        "--sarif-root",
        type=Path,
        help=(
            "Repository root used to produce relative SARIF artifact URIs; "
            "valid only with --format sarif"
        ),
    )
    _add_diagnostic_format(preflight_parser)
    return parser


def _parse_layer_names(values: list[str]) -> set[str]:
    names: set[str] = set()
    for value in values:
        name = value.strip()
        if not name or name in names:
            raise StarshineError(f"invalid or duplicate layer name: {name!r}")
        names.add(name)
    return names


def _reject_output_collision(
    output: Path | None,
    protected_paths: tuple[Path, ...],
    *,
    message: str,
) -> None:
    if output is None:
        return
    resolved_output = output.resolve()
    if any(resolved_output == protected.resolve() for protected in protected_paths):
        raise StarshineError(message)


def _repository_relative_uri(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise StarshineError("SARIF workflow and input paths must be contained by --sarif-root") from exc
    uri = relative.as_posix()
    if not uri or uri == ".":
        raise StarshineError("SARIF artifact paths must identify files below --sarif-root")
    return uri


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


def _doctor_command(args: argparse.Namespace) -> int:
    if args.output is not None and args.output.exists() and args.output.is_dir():
        raise StarshineError("doctor output must not identify a directory")
    report = build_doctor_report(require_geopackage=args.require_geopackage)
    content = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.format == "json"
        else render_doctor_text(report)
    )
    if args.output is None:
        print(content, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(args.output)
    return 0 if report["valid"] else 1


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
    _reject_output_collision(
        args.output,
        (args.source,),
        message="inspection output must not overwrite the source GeoJSON",
    )
    report = inspect_feature_collection(read_json(args.source))
    if args.output is None:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        write_json(report, args.output)
        print(args.output)
    return 0


def _inventory_command(args: argparse.Namespace) -> int:
    _reject_output_collision(
        args.output,
        (args.source,),
        message="inventory output must not overwrite the source",
    )
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


def _quality_command(args: argparse.Namespace) -> int:
    _reject_output_collision(
        args.output,
        (args.source,),
        message="geometry-quality output must not overwrite the source GeoJSON",
    )
    report = assess_geometry_quality(read_json(args.source))
    if args.format == "json":
        content = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        content = render_geometry_quality_markdown(report)

    if args.output is None:
        print(content, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(args.output)
    return 0 if report["valid"] else 1


def _operators_command(args: argparse.Namespace) -> int:
    catalog = operator_catalog()
    if args.output is None:
        print(json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        write_json(catalog, args.output)
        print(args.output)
    return 0


def _plan_command(args: argparse.Namespace) -> int:
    _reject_output_collision(
        args.output,
        (args.workflow,),
        message="workflow plan output must not overwrite the workflow file",
    )
    workflow = read_json(args.workflow)
    plan = plan_workflow(workflow, _parse_layer_names(args.layer_name))
    if args.output is None:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        write_json(plan, args.output)
        print(args.output)
    return 0


def _graph_command(args: argparse.Namespace) -> int:
    _reject_output_collision(
        args.output,
        (args.workflow,),
        message="workflow graph output must not overwrite the workflow file",
    )
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
    _reject_output_collision(
        args.output,
        (args.workflow,),
        message="workflow explanation output must not overwrite the workflow file",
    )
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


def _contract_command(args: argparse.Namespace) -> int:
    _reject_output_collision(
        args.output,
        (args.workflow,),
        message="workflow contract output must not overwrite the workflow file",
    )
    workflow = read_json(args.workflow)
    contract = build_workflow_contract(workflow, _parse_layer_names(args.layer_name))
    if args.format == "json":
        content = json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        content = render_workflow_contract_markdown(contract)

    if args.output is None:
        print(content, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(args.output)
    return 0


def _preflight_command(args: argparse.Namespace) -> int:
    if args.format != "sarif" and args.sarif_root is not None:
        raise StarshineError("--sarif-root requires --format sarif")
    if args.format == "sarif":
        if args.sarif_root is None:
            raise StarshineError("--format sarif requires --sarif-root")
        if not args.sarif_root.is_dir():
            raise StarshineError("--sarif-root must identify an existing directory")

    bindings = prepare_layer_bindings(args.layer, args.geopackage_layer)
    paths = bindings.paths
    _reject_output_collision(
        args.output,
        (args.workflow,),
        message="workflow preflight output must not overwrite the workflow file",
    )
    _reject_output_collision(
        args.output,
        tuple(paths.values()),
        message="workflow preflight output must not overwrite an input layer",
    )

    workflow_uri: str | None = None
    artifact_uris: dict[str, str] | None = None
    if args.format == "sarif":
        root = args.sarif_root
        workflow_uri = _repository_relative_uri(args.workflow, root)
        artifact_uris = {
            name: _repository_relative_uri(path, root) for name, path in paths.items()
        }

    workflow = read_json(args.workflow)
    report = preflight_workflow_inputs(workflow, bindings.load())
    if args.format == "json":
        content = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    elif args.format == "sarif":
        if workflow_uri is None or artifact_uris is None:
            raise RuntimeError("SARIF paths were not prepared before report conversion")
        sarif = build_workflow_preflight_sarif(
            report,
            artifact_uris,
            automation_id=f"starshine/preflight/{workflow_uri}",
        )
        content = json.dumps(sarif, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        content = render_workflow_preflight_markdown(report)

    if args.output is None:
        print(content, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(args.output)
    return 0 if report["valid"] else 1


def _run_command(args: argparse.Namespace) -> int:
    bindings = prepare_layer_bindings(args.layer, args.geopackage_layer)
    input_paths = tuple(bindings.paths.values())
    output = prepare_run_output(
        args.output,
        output_format=args.output_format,
        geopackage_layer=args.geopackage_output_layer,
        overwrite=args.overwrite_output,
        workflow_path=args.workflow,
        input_paths=input_paths,
        manifest_path=args.manifest,
    )

    workflow = read_json(args.workflow)
    layers = bindings.load()
    results = run_workflow(workflow, layers)
    if args.output_layer not in results:
        raise StarshineError(f"workflow did not produce layer: {args.output_layer}")
    output_layer = results[args.output_layer]
    output.write(output_layer, input_paths=input_paths)
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
        if args.command == "doctor":
            return _doctor_command(args)
        if args.command == "validate":
            return _validate_command(args)
        if args.command == "inspect":
            return _inspect_command(args)
        if args.command == "inventory":
            return _inventory_command(args)
        if args.command == "quality":
            return _quality_command(args)
        if args.command == "operators":
            return _operators_command(args)
        if args.command == "plan":
            return _plan_command(args)
        if args.command == "graph":
            return _graph_command(args)
        if args.command == "explain":
            return _explain_command(args)
        if args.command == "contract":
            return _contract_command(args)
        if args.command == "preflight":
            return _preflight_command(args)
        return _run_command(args)
    except StarshineError as exc:
        _print_error(exc, getattr(args, "diagnostic_format", "text"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
