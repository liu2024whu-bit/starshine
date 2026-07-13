# Starshine Geo

[![CI](https://github.com/liu2024whu-bit/starshine/actions/workflows/ci.yml/badge.svg)](https://github.com/liu2024whu-bit/starshine/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-research%20preview-orange.svg)](ROADMAP.md)

Starshine Geo is a small, auditable open-source core for reproducible spatial-analysis workflows. It focuses on the parts that must remain explicit in GIS automation: coordinate-reference-system handling, geometry validation, bounded operator registries, parameter checks, reproducible examples, and testable results.

This repository is **not a temporary application-only demo**. It is the independently maintained public core extracted from a longer-running private spatial-intelligence research project. The full research system contains unreleased datasets and experimental modules; this public repository contains only code and self-created sample data that can be safely maintained in the open. See [Project history and provenance](docs/PROJECT_HISTORY.md).

## Why this project exists

Spatial workflows often fail silently when geographic coordinates are treated as metres, invalid geometries enter overlays, output names overwrite inputs, or natural-language planners call unregistered functions. Starshine makes those boundaries visible and executable.

The initial public release provides:

- validated GeoJSON FeatureCollection input;
- projected-CRS checks for distance-based work;
- buffer, dissolve, and point-within-polygon summary operators;
- a versioned JSON workflow format and machine-readable schema;
- structured preflight diagnostics before execution;
- an explicit operator registry with no dynamic `eval`;
- optional path-free reproducibility manifests;
- an optional GeoPackage adapter contract with explicit layer, CRS, and overwrite rules;
- self-created sample data and a reproducible command-line demo;
- tests across supported Python versions.

## Install

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

## Run the demo

```bash
starshine run examples/workflow.json \
  --layer zones=examples/data/zones.geojson \
  --layer sites=examples/data/sites.geojson \
  --output-layer zone_summary \
  --output examples/output/zone_summary.geojson \
  --manifest examples/output/zone_summary.manifest.json
```

The `--manifest` option is optional. When supplied, it records deterministic workflow, input,
step, output, version, and CRS evidence without copying feature content or CLI file paths. See
[Reproducibility manifests](docs/REPRODUCIBILITY.md).

Or:

```bash
python examples/run_demo.py
```

The output preserves each study-zone polygon and adds a `site_count` property. The included sample should produce `2` for the west zone and `1` for the east zone.

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

Only registered operators can run. Each step must write to a new layer name, so input data cannot be overwritten accidentally. See the [workflow schema](schemas/workflow-v1.schema.json) and [validation contract](docs/WORKFLOW_VALIDATION.md).

## Optional GeoPackage boundary

The public adapter converts selected GeoPackage layers to and from the same validated in-memory
GeoJSON contract used by the workflow engine. Multi-layer packages require an explicit layer,
CRS metadata is preserved and validated, and existing or input-file destinations require an
explicit overwrite flag. See [GeoPackage adapter contract](docs/GEOPACKAGE.md).

## Project status

Starshine Geo is an alpha-quality research preview. The API is intentionally small while the maintainers establish stable contracts, external reproduction, issue triage, and release discipline. The public core will remain open and maintained independently from unreleased private research modules.

See [ROADMAP.md](ROADMAP.md), [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and [architecture notes](docs/ARCHITECTURE.md).

## Scope and data

All sample GeoJSON in this repository was created specifically for this public project. No private database dump, credential, textbook PDF, OCR derivative, proprietary dataset, or machine-specific path is included. See [Open-source scope](docs/OPEN_SOURCE_SCOPE.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
