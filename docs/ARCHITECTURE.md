# Architecture

Starshine uses a deliberately small modular architecture.

- `geojson.py` validates and normalizes the public data contract.
- `inspection.py` produces deterministic collection-level reports after validation.
- `geometry_quality.py` is the compact public facade for read-only geometry-quality assessment.
- `_geometry_quality_model.py` owns the report version/type; `_geometry_quality_findings.py` owns bounded aggregation.
- `_geometry_quality_coordinates.py` inspects coordinate structure without retaining positions.
- `_geometry_quality_report.py` owns CRS metadata, geometry checks, duplicate grouping, counts, and digests.
- `_geometry_quality_render.py` renders completed reports without importing geometry or checker code.
- `crs.py` centralizes CRS parsing, projected-coordinate requirements, and transforms.
- `operators.py` implements independently testable transformation, overlay, attribution, summary,
  and proximity operations.
- `metrics.py` keeps projected geometry measurement logic isolated from topology-changing operators.
- `operator_registry.py` binds reviewed executors to public input, parameter, default, and sensitivity contracts.
- `workflow.py` maps versioned JSON steps to an explicit operator registry.
- `planning.py` produces deterministic data-free dependency and layer-provenance reports.
- `graph.py` converts canonical plans into schema-checked JSON and safe Mermaid views.
- `explain.py` turns canonical plan and graph evidence into structured and Markdown explanations.
- `contract_specs.py` stores declarative per-input data requirements; `contracts.py` resolves them against canonical plans.
- `preflight.py` is the compact public facade for actual-input checking and Markdown rendering.
- `_preflight_model.py` owns the report version, type alias, and shared execution-time limitations.
- `_preflight_findings.py` aggregates repeated findings without retaining property values.
- `_preflight_checks.py` owns per-layer structure, geometry, CRS, and field checks.
- `_preflight_report.py` coordinates contracts, cross-layer equivalence, counts, and report digests.
- `_preflight_render.py` renders completed reports without importing validation or geometry code.
- `preflight_sarif.py` consumes the public facade and converts completed reports to deterministic SARIF.
- `cli.py` provides reproducible file-based execution and explicit file-format adaptation.

The workflow layer does not import functions from arbitrary module names and does not use `eval`, `exec`, shell commands, or user-provided Python. Each operator returns an in-memory FeatureCollection; the CLI is the only component that writes a selected result to disk.

## Geometry Quality dependency direction

Geometry Quality follows a separate one-way import graph:

`geometry_quality.py → _geometry_quality_report.py → _geometry_quality_coordinates.py / _geometry_quality_findings.py / _geometry_quality_model.py`

`geometry_quality.py → _geometry_quality_render.py → _geometry_quality_model.py`

The report builder does not import Workflow, operators, Preflight, or the renderer. The renderer does
not import CRS, GeoJSON, Shapely, or report assembly. Internal modules never import the public facade.
Focused AST tests enforce this graph so geometry diagnostics remain independent from workflow input
contracts and future file adapters.

## Workflow Preflight dependency direction

The Preflight implementation follows one import direction:

`preflight.py → _preflight_report.py → _preflight_checks.py / _preflight_findings.py`

`preflight.py → _preflight_render.py → _preflight_model.py`

`preflight_sarif.py → preflight.py`

The model and finding modules do not import the facade. Rendering does not import contracts, CRS,
GeoJSON, geometry, or report assembly. SARIF does not reach into checker internals. Focused AST-based
tests enforce this graph so a later GeoPackage adapter or geometry-quality report cannot create a
second validation path or an import cycle.

## Design principles

1. **GIS semantics before convenience.** Distance work must declare a projected CRS.
2. **Small operators.** Each operation has one independently testable responsibility.
3. **Declarative extension.** Runtime execution, defaults, parameter validation, input contracts, input preflight, planning, and catalog metadata share one reviewed registry entry.
4. **Explicit failure.** Invalid geometry, missing fields, and unsupported operations fail with actionable errors.
5. **Reproducibility.** A workflow, named inputs, package version, and output layer are sufficient to repeat the included demo.
6. **Public/private separation.** Experimental modules and unreleased data do not silently leak into the public core.
7. **Output adapters stay separate.** Format-specific conversion such as Mermaid, Markdown, and SARIF must not become a second validation or execution path.
8. **Teaching artifacts stay external to runtime.** Intentional failures live under `examples/teaching/` and exercise public contracts without becoming package dependencies.
9. **Diagnosis is not repair.** Geometry-quality reports expose invalid, empty, duplicate, or dimensionally inconsistent geometry but never modify source data.
