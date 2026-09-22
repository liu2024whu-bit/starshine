# Starshine Geo

[![CI](https://github.com/liu2024whu-bit/starshine/actions/workflows/ci.yml/badge.svg)](https://github.com/liu2024whu-bit/starshine/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-0.7.0.dev0%20development%20snapshot-blue.svg)](ROADMAP.md)

Starshine Geo is a small, auditable open-source core for reproducible spatial-analysis workflows.
It keeps the parts of GIS automation that are easy to hide—CRS assumptions, geometry contracts,
operator registration, input preparation, output provenance, and distribution evidence—explicit and
testable.

The repository is intentionally bounded. It is not a general-purpose desktop GIS and it does not try
to maximize operator count. New behavior is expected to reuse the public registry, workflow,
Preflight, testing, evidence, and release boundaries instead of creating parallel execution paths.

## What the current development snapshot provides

- validated GeoJSON FeatureCollection input and explicit CRS handling;
- a bounded declarative operator registry with no dynamic `eval`;
- buffer, dissolve, point summary, reprojection, clip/difference, pairwise intersection,
  nearest-feature matching, point-in-polygon join, and projected geometry metrics;
- deterministic Workflow validation, planning, graph, Explain, contract, and Preflight reports;
- SARIF 2.1.0 export for completed Preflight findings;
- read-only source inventory, GeoJSON inspection, and geometry-quality reports;
- optional GeoPackage input/output with explicit layer selection and overwrite protection;
- deterministic manifests, synthetic benchmark evidence, and path-free runtime diagnostics;
- self-created reproduction fixtures and clean installed-wheel checks;
- Python 3.10–3.14 source and built-wheel CI evidence, with clean Linux, Windows, and macOS
  reproduction on Python 3.14.

Detailed semantics live in the owned documentation pages rather than in this landing page. Start with
the [documentation index](docs/README.md).

## Install for development

Create an isolated environment and install the development extras:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

GeoPackage support is optional:

```bash
python -m pip install -e ".[geopackage]"
```

Check the installed package and spatial runtime:

```bash
starshine --version
starshine doctor
```

For a clean-environment verification path, see
[REPRODUCING.md](docs/REPRODUCING.md).

## Quick start

Inspect the public operator catalog:

```bash
starshine operators
```

Validate and preflight a workflow before running it:

```bash
starshine validate examples/plan.workflow.json \
  --layer-name source \
  --layer-name mask

starshine preflight examples/plan.workflow.json \
  --layer source=examples/data/clip-source.geojson \
  --layer mask=examples/data/clip-mask.geojson
```

Run the included synthetic demo:

```bash
starshine run examples/workflow.json \
  --layer zones=examples/data/zones.geojson \
  --layer sites=examples/data/sites.geojson \
  --output-layer zone_summary \
  --output examples/output/zone_summary.geojson \
  --manifest examples/output/zone_summary.manifest.json
```

Reproduce the public core from self-created temporary data:

```bash
python scripts/reproduce_installed_core.py --output reproduction-report.json
```

The reproduction harness exercises the installed CLI and public API across doctor, validation,
planning, contracts, Preflight, execution, inspection, geometry quality, the operator catalog, and
manifest generation.

## Documentation

Use the [documentation index](docs/README.md) as the ownership map. The most common entry points are:

| Need | Authoritative document |
| --- | --- |
| Understand module boundaries | [Architecture](docs/ARCHITECTURE.md) |
| Install and reproduce from a clean environment | [Reproducing Starshine](docs/REPRODUCING.md) |
| Understand operators and extension rules | [Operator registry](docs/OPERATORS.md) |
| Validate and prepare workflows | [Workflow validation](docs/WORKFLOW_VALIDATION.md), [planning](docs/WORKFLOW_PLANNING.md), [contracts](docs/WORKFLOW_CONTRACTS.md), [Preflight](docs/WORKFLOW_PREFLIGHT.md) |
| Work with GeoPackage | [GeoPackage](docs/GEOPACKAGE.md) |
| Inspect sources or geometry quality | [Inspection](docs/INSPECTION.md), [geometry quality](docs/GEOMETRY_QUALITY.md), [vector quality gate](docs/VECTOR_QUALITY_GATE.md) |
| Understand indexing and performance evidence | [Spatial indexing](docs/SPATIAL_INDEXING.md), [benchmarks](docs/BENCHMARKS.md) |
| Build and verify distributions | [Release process](docs/RELEASE_PROCESS.md) |
| Understand public-data and provenance boundaries | [Open-source scope](docs/OPEN_SOURCE_SCOPE.md), [project history](docs/PROJECT_HISTORY.md) |

Operator-specific contracts such as
[clip/difference](docs/CLIP.md),
[intersection](docs/INTERSECTION.md),
[nearest matching](docs/NEAREST.md),
[spatial join](docs/SPATIAL_JOIN.md), and
[geometry metrics](docs/GEOMETRY_METRICS.md)
remain short normative references.

## Verification model

Source-checkout tests and installed-wheel tests answer different questions. Pull-request and
`main` CI therefore verify both the source tree and the exact built distribution.

The current public evidence includes:

- source tests on Python 3.10–3.14;
- clean normal-wheel checks on Python 3.10–3.14;
- clean GeoPackage-extra wheel checks on Python 3.10–3.14;
- Linux, Windows, and macOS reproduction using Python 3.14;
- constrained validation-tool CI plus a separate Latest Compatible Dependencies workflow;
- deterministic tracked workflow evidence checked by `scripts/refresh_public_evidence.py`;
- a portable clean-wheel reproduction bundle for handoff to an external machine or CI project;
- release-readiness, Twine, archive-content, and public-repository audits;
- a workflow audit rule that rejects diagnostic `tee` pipelines without `set -o pipefail`.

See [REPRODUCING.md](docs/REPRODUCING.md) for end-to-end reproduction and
[RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md) for distribution evidence.

## Public development boundary

Tracked examples and benchmark geometries are synthetic or created specifically for this repository.
Private databases, credentials, unpublished modules, personal paths, textbook/OCR material, and
research-delivery artifacts are outside the public boundary.

The repository audit and release-archive inspection enforce important parts of that boundary. See
[OPEN_SOURCE_SCOPE.md](docs/OPEN_SOURCE_SCOPE.md) and
[PROJECT_HISTORY.md](docs/PROJECT_HISTORY.md).

## Releases

`pyproject.toml` identifies the artifact currently being built. Development snapshots use a PEP 440
`.devN` version so CI artifacts cannot be confused with the latest stable release.

The current stable snapshot is documented in
[0.4.0 release notes](docs/releases/0.4.0.md) and the [changelog](CHANGELOG.md).
Release preparation and artifact verification are defined in
[RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md).

## Project status

Starshine Geo 0.7.0.dev0 is the current development snapshot. It contains reviewed changes recorded
under `[Unreleased]` and is not a tagged 0.7.0 release. The latest stable release metadata remains
0.4.0. The public API remains intentionally bounded while maintainers strengthen reproducibility,
release discipline, and independently useful spatial-analysis workflows.

See [ROADMAP.md](ROADMAP.md), [CONTRIBUTING.md](CONTRIBUTING.md),
[SECURITY.md](SECURITY.md), and [architecture notes](docs/ARCHITECTURE.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
