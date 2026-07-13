# Starshine Geo

[![CI](https://github.com/liu2024whu-bit/starshine/actions/workflows/ci.yml/badge.svg)](https://github.com/liu2024whu-bit/starshine/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-0.2.0%20research%20preview-orange.svg)](ROADMAP.md)

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

The public 0.2 line provides:

- validated GeoJSON FeatureCollection input;
- projected-CRS checks for distance-based work;
- buffer, dissolve, and point-within-polygon summary operators;
- a versioned JSON workflow format and operator-specific machine-readable schema;
- structured preflight diagnostics for structure, inputs, parameters, and CRS rules;
- an explicit operator registry with no dynamic `eval`;
- optional path-free reproducibility manifests;
- optional GeoPackage input/output with explicit layer, CRS, and overwrite rules;
- deterministic GeoJSON inspection reports with counts, bounds, CRS, fields, and digests;
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
[release process](docs/RELEASE_PROCESS.md), [0.2.0 release notes](docs/releases/0.2.0.md), and
[changelog](CHANGELOG.md).

## Project status

Starshine Geo 0.2.0 is an alpha-quality research preview. The API is intentionally small while the
maintainers establish stable contracts, external reproduction, issue triage, release discipline,
and independent community use.

See [ROADMAP.md](ROADMAP.md), [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and
[architecture notes](docs/ARCHITECTURE.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
