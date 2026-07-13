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
- self-created sample data and reproducible command-line examples;
- public-boundary, package-build, and Python 3.10–3.12 CI checks.

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

All tracked sample GeoJSON, workflow fixtures, and GeoPackage round-trip data are created for this
repository. Current changes must be specified through public issues and implemented from public
code. Private databases, credentials, unpublished modules, personal paths, textbook/OCR material,
and research-delivery artifacts are excluded.

CI runs `scripts/audit_public_repository.py` on every pull request and separately inspects wheel and
source-distribution members. See [Open-source scope](docs/OPEN_SOURCE_SCOPE.md) and
[project provenance](docs/PROJECT_HISTORY.md).

## Releases

Version metadata is sourced from `pyproject.toml`, while runtime code reads the installed package
metadata. CI builds and checks one wheel and one source distribution before a release can be tagged.
See the [release process](docs/RELEASE_PROCESS.md), [0.2.0 release notes](docs/releases/0.2.0.md),
and [changelog](CHANGELOG.md).

## Project status

Starshine Geo 0.2.0 is an alpha-quality research preview. The API is intentionally small while the
maintainers establish stable contracts, external reproduction, issue triage, release discipline,
and independent community use.

See [ROADMAP.md](ROADMAP.md), [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and
[architecture notes](docs/ARCHITECTURE.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
