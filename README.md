# Starshine Geo

[![CI](https://github.com/liu2024whu-bit/starshine/actions/workflows/ci.yml/badge.svg)](https://github.com/liu2024whu-bit/starshine/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-0.3.0%20research%20preview-orange.svg)](ROADMAP.md)

Starshine Geo is a small, auditable open-source core for reproducible spatial-analysis workflows.
It focuses on the parts that must remain explicit in GIS automation: coordinate-reference-system
handling, geometry validation, bounded operator registries, parameter checks, reproducible
examples, and testable results.

This repository is not a temporary application-only demo. It is a permanently public project with
its own issues, pull requests, CI, release process, and synthetic fixtures. Historical provenance is
documented separately, but current Starshine development is based on this public repository rather
than private source code or datasets.

## Why this project exists

Spatial workflows often fail silently when geographic coordinates are treated as metres, invalid
geometries enter overlays, output names overwrite inputs, or planners call unregistered functions.
Starshine makes those boundaries visible, machine-readable, and executable.

The public 0.3 line provides:

- validated GeoJSON FeatureCollection input;
- projected-CRS checks for distance-based work;
- buffer, dissolve, point-within-polygon summary and join, projected geometry metrics, explicit
  reprojection, CRS-safe clipping, and deterministic nearest-feature matching;
- a versioned JSON workflow format and operator-specific machine-readable schema;
- structured workflow diagnostics for structure, inputs, parameters, and CRS rules;
- a declarative operator registry and machine-readable catalog with no dynamic `eval`;
- deterministic data-free workflow plans with dependencies, defaults, layer provenance, and digests;
- schema-checked JSON workflow graphs and safely escaped Mermaid dependency views;
- data-free Workflow Explain reports with parameter provenance and review-ready Markdown;
- planner-derived external-layer contracts for geometry, CRS, and property preparation;
- actual input preflight reports for geometry, CRS, field, uniqueness, and collision checks;
- optional path-free reproducibility manifests;
- optional GeoPackage input/output with explicit layer, CRS, and overwrite rules;
- deterministic GeoJSON inspection reports with counts, bounds, CRS, fields, and digests;
- synthetic teaching cases for CRS misuse, invalid geometry, and malformed properties;
- a deterministic synthetic small-vector benchmark corpus with schema-checked JSON reports;
- self-created sample data and reproducible command-line examples;
- public-boundary, package-build, and Python 3.10–3.12 source and built-wheel CI checks.

## Install for development

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

GeoPackage support is kept outside the base dependency set:

```bash
python -m pip install -e ".[geopackage]"
```

Check the installed version:

```bash
starshine --version
```

## Verify a built wheel

Editable source tests and installed-wheel tests answer different questions. The source suite checks
implementation behavior during development; the wheel smoke test proves that the published package
contains its required modules, declares its runtime dependencies, and exposes the CLI correctly.

After building a wheel, install it non-editably and run the public smoke script:

```bash
python -m build
python -m pip install --force-reinstall dist/*.whl
python scripts/smoke_installed_wheel.py
```

In CI, the wheel is built once and downloaded into clean Python 3.10, 3.11, and 3.12 jobs that do not
check out the repository. See the [release process](docs/RELEASE_PROCESS.md) for the exact checks.

## Discover supported operators

The runtime registry is available as a schema-checked JSON catalog:

```bash
starshine operators
starshine operators --output operators.json
```

The same value is available through `operator_catalog()`. Runtime executors and validators are not
serialized into the report. See the [operator registry and extension contract](docs/OPERATORS.md) and
[operator catalog schema](schemas/operator-catalog-v1.schema.json).

## Plan a workflow without reading feature data

The planner validates a workflow, resolves registry defaults, and reports its dependency graph and
layer provenance without loading GeoJSON or running operators:

```bash
starshine plan examples/plan.workflow.json \
  --layer-name source \
  --layer-name mask
```

Plans include Workflow and Operator Catalog digests, required and unused external layers, ordered
step dependencies, resolved parameter sources, terminal outputs, and declared output-CRS behavior.
See [workflow planning](docs/WORKFLOW_PLANNING.md) and the
[workflow plan schema](schemas/workflow-plan-v1.schema.json).

## Render a workflow graph for review or teaching

The graph command derives a compact dependency view from the canonical plan without reading feature
data or exposing parameter values:

```bash
starshine graph examples/plan.workflow.json \
  --layer-name source \
  --layer-name mask
```

Mermaid is the default output. Use `--format json` for a schema-checked graph report suitable for CI
or a user interface. See [workflow graphs](docs/WORKFLOW_GRAPH.md), the
[workflow graph schema](schemas/workflow-graph-v1.schema.json), and the tracked
[Mermaid example](examples/plan.workflow.mmd).

## Explain a workflow for review or teaching

The explain command converts the canonical plan and graph evidence into a step-by-step Markdown
narrative without loading feature data:

```bash
starshine explain examples/plan.workflow.json \
  --layer-name source \
  --layer-name mask \
  --layer-name unused
```

Use `--format json` for a Schema-checked explanation report containing input provenance, direct
dependencies, provided/default parameter sources, output-CRS behavior, terminal outputs, and
execution-time limitations. See [workflow explanations](docs/WORKFLOW_EXPLAIN.md), the
[explanation schema](schemas/workflow-explanation-v1.schema.json), and the tracked
[Markdown example](examples/plan.workflow.explanation.md).

## Prepare external layers with a workflow contract

The contract command converts registry input metadata and the canonical plan into a deterministic
checklist without reading feature data:

```bash
starshine contract examples/plan.workflow.json \
  --layer-name source \
  --layer-name mask \
  --layer-name unused
```

Markdown is the default output. Use `--format json` for a schema-checked report suitable for CI or a
data-loading interface. See [workflow input contracts](docs/WORKFLOW_CONTRACTS.md), the
[contract schema](schemas/workflow-contract-v1.schema.json), and the tracked
[Markdown example](examples/plan.workflow.contract.md).

## Preflight actual workflow inputs

The preflight command loads external GeoJSON layers and checks them against the planner-derived
contract without executing spatial operators:

```bash
starshine preflight examples/plan.workflow.json \
  --layer source=examples/data/clip-source.geojson \
  --layer mask=examples/data/clip-mask.geojson
```

Markdown is the default output. Use `--format json` for a schema-checked CI report. A completed
preflight returns exit code `0` when valid and `1` when contract violations are reported. See
[workflow input preflight](docs/WORKFLOW_PREFLIGHT.md), the
[preflight schema](schemas/workflow-preflight-v1.schema.json), and the tracked
[Markdown example](examples/plan.workflow.preflight.md).

## Inspect a GeoJSON collection without running a workflow

The inspection command validates one `FeatureCollection` and reports structure without copying
feature coordinates or property values into the report:

```bash
starshine inspect examples/data/zones.geojson
```

Write the same schema-checked report to a file:

```bash
starshine inspect examples/data/zones.geojson \
  --output zones.inspection.json
```

Reports include feature and geometry counts, sorted property fields, declared CRS, collection
bounds, and a deterministic collection digest. See the
[inspection contract](docs/INSPECTION.md) and
[inspection report schema](schemas/inspection-report-v1.schema.json).

## Learn from intentional CRS and geometry failures

The files under `examples/teaching/` are deliberately small and several are intentionally invalid.
They demonstrate geographic coordinates incorrectly used as a buffer working CRS, a corrected
projected workflow, a self-intersecting polygon, an empty geometry, and malformed Feature
properties.

Run the complete documented check set:

```bash
python scripts/verify_teaching_examples.py
```

Each failure has an exact command, expected exit code, and stable message fragment or diagnostic path.
The corrected examples use only synthetic data and produce reviewable inspection or workflow
summaries. See [synthetic failure examples](docs/TEACHING_FAILURES.md).

## Validate a workflow without running it

The validation command needs only the workflow JSON and the names of layers that will be available.
It does not read feature data or execute spatial operators.

```bash
starshine validate tests/fixtures/workflows/valid-buffer.json \
  --layer-name source
```

For automation, request a stable JSON diagnostic envelope:

```bash
starshine validate tests/fixtures/workflows/invalid-buffer-missing-work-crs.json \
  --layer-name source \
  --diagnostic-format json
```

See the [workflow validation contract](docs/WORKFLOW_VALIDATION.md).

## Run the demo

```bash
starshine run examples/workflow.json \
  --layer zones=examples/data/zones.geojson \
  --layer sites=examples/data/sites.geojson \
  --output-layer zone_summary \
  --output examples/output/zone_summary.geojson \
  --manifest examples/output/zone_summary.manifest.json
```

The `--manifest` option is optional. When supplied, it records deterministic workflow, input, step,
output, version, and CRS evidence without copying feature content or CLI file paths. See
[Reproducibility manifests](docs/REPRODUCIBILITY.md).

Or:

```bash
python examples/run_demo.py
```

The output preserves each study-zone polygon and adds a `site_count` property. The included sample
should produce `2` for the west zone and `1` for the east zone.

## Run deterministic public benchmarks

The benchmark corpus is generated entirely from Starshine's public operators and synthetic
geometries. Correctness verification is separate from timing observations:

```bash
python -m benchmarks.verify
python -m benchmarks.run --repeat 5 --output benchmark-report.json
python scripts/check_benchmark_report.py benchmark-report.json
```

Reports include corpus, case, and output digests; feature and operation counts; environment metadata;
and validation and validated-run timing samples. CI validates the report schema and deterministic
fields but deliberately does not impose fragile wall-clock thresholds. See
[benchmark documentation](docs/BENCHMARKS.md).

## Workflow format

```json
{
  "version": 1,
  "steps": [
    {
      "operation": "summarize_points_within",
      "inputs": {"polygons": "zones", "points": "sites"},
      "parameters": {"polygon_id_field": "id", "count_field": "site_count"},
      "output": "zone_summary"
    }
  ]
}
```

Only registered operators can run. Each step must write to a new layer name, so input data cannot
be overwritten accidentally. See the [workflow schema](schemas/workflow-v1.schema.json) and
[validation contract](docs/WORKFLOW_VALIDATION.md).

A tracked reprojection example transforms the synthetic teaching points to `EPSG:3857`:

```bash
starshine run examples/reproject.workflow.json \
  --layer source=examples/teaching/geographic-points.geojson \
  --output-layer projected \
  --output examples/output/projected-points.geojson
```

Reprojection preserves feature order and properties, requires an explicit target CRS, and refuses a
`source_crs` parameter that conflicts with the collection's declared `starshine:crs`.

## Clip features with an explicit polygon mask

The `clip` operator intersects each source feature with the union of one polygon mask collection.
Both collections must declare equivalent CRS values; clipping never hides an implicit reprojection:

```bash
starshine run examples/clip.workflow.json \
  --layer source=examples/data/clip-source.geojson \
  --layer mask=examples/data/clip-mask.geojson \
  --output-layer clipped \
  --output examples/output/clipped.geojson
```

The operation preserves source property objects and retained feature order, drops empty
intersections, and retains valid boundary-only intersections. See the
[clip contract](docs/CLIP.md).

## Match each feature to its nearest candidate

The `nearest` operator compares source and candidate geometries in one equivalent projected CRS,
preserves every source feature, and adds deterministic match and distance fields:

```bash
starshine run examples/nearest.workflow.json \
  --layer sources=examples/data/nearest-source.geojson \
  --layer facilities=examples/data/nearest-candidates.geojson \
  --output-layer nearest_facilities \
  --output examples/output/nearest-facilities.geojson
```

Equal-distance ties use candidate input order. Empty candidate collections and matches beyond an
optional inclusive distance limit produce explicit `null` fields instead of dropping source
features. See the [nearest-feature contract](docs/NEAREST.md).

## Calculate projected geometry metrics

The `geometry_metrics` operation adds area and length fields without changing feature geometry:

```bash
starshine run examples/geometry-metrics.workflow.json \
  --layer features=examples/data/metric-features.geojson \
  --output-layer measured \
  --output examples/output/measured-features.geojson
```

The input must declare a projected CRS, and output fields must not collide with source properties.
See the [geometry metrics contract](docs/GEOMETRY_METRICS.md).

## Join points to polygons with explicit ambiguity handling

The `join_points_to_polygons` operator preserves every point and attaches one polygon identifier
using boundary-inclusive `covers` semantics:

```bash
starshine run examples/spatial-join.workflow.json \
  --layer points=examples/data/join-points.geojson \
  --layer zones=examples/data/join-polygons.geojson \
  --output-layer joined_points \
  --output examples/output/joined-points.geojson
```

Ambiguous overlaps and shared-boundary matches fail by default. Workflows may explicitly select the
deterministic `first` policy when polygon input order is an intentional priority rule. Unmatched
points remain in the output with a configured scalar or `null` value. See the
[point-in-polygon join contract](docs/SPATIAL_JOIN.md).


## Optional GeoPackage boundary

The public adapter converts selected GeoPackage layers to and from the same validated in-memory
GeoJSON contract used by the workflow engine. Multi-layer packages require an explicit layer, CRS
metadata is preserved and validated, and existing or input-file destinations require an explicit
overwrite flag. See [GeoPackage adapter contract](docs/GEOPACKAGE.md).

## Public development boundary

All tracked sample GeoJSON, workflow fixtures, generated benchmark geometries, and GeoPackage
round-trip data are created for this repository. Current changes must be specified through public
issues and implemented from public code. Private databases, credentials, unpublished modules,
personal paths, textbook/OCR material, and research-delivery artifacts are excluded.

CI runs `scripts/audit_public_repository.py` on every pull request and separately inspects wheel and
source-distribution members. See [Open-source scope](docs/OPEN_SOURCE_SCOPE.md) and
[project provenance](docs/PROJECT_HISTORY.md).

## Releases

Version metadata is sourced from `pyproject.toml`, while runtime code reads the installed package
metadata. CI builds and inspects one wheel and one source distribution, then installs the exact wheel
in clean supported-Python jobs before a release can be tagged. See the
[release process](docs/RELEASE_PROCESS.md), [0.3.0 release notes](docs/releases/0.3.0.md), and
[changelog](CHANGELOG.md).

## Project status

Starshine Geo 0.3.0 is an alpha-quality research preview. The API is intentionally small while the
maintainers establish stable contracts, external reproduction, issue triage, release discipline,
and independent community use.

See [ROADMAP.md](ROADMAP.md), [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and
[architecture notes](docs/ARCHITECTURE.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
