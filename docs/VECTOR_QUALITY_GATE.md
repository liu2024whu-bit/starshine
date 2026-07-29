# Reproducible vector quality gate

This recipe combines Starshine's read-only diagnostics and bounded workflow tools into a practical
quality gate for small public or research vector datasets. It is suitable for local review and CI,
but it deliberately does not modify the source data.

## Stage 1: diagnose geometry

```bash
starshine quality examples/geometry-quality.geojson \
  --format json \
  --output geometry-quality.report.json
```

The tracked example intentionally returns exit code `1`. The report records a self-intersecting
polygon, an empty polygon, one duplicate point group, both 2D and 3D geometries, and missing CRS
metadata without copying feature properties or coordinates.

A production pipeline can stop on exit code `1`, archive the JSON report, and route the source data
for a domain-specific correction process. Starshine does not choose a repair operation.

## Stage 2: inspect a corrected collection

After correction outside Starshine, inspect the collection-level structure:

```bash
starshine inspect examples/data/clip-source.geojson \
  --output clip-source.inspection.json
```

Inspection requires strictly valid geometry and records the collection digest, geometry counts,
fields, CRS, bounds, and feature count. The canonical digest can be used to prove which JSON value was reviewed; it is not a digest of
source-file whitespace or key order.

## Stage 3: validate workflow intent without data access

```bash
starshine validate examples/clip.workflow.json \
  --layer-name source \
  --layer-name mask

starshine plan examples/clip.workflow.json \
  --layer-name source \
  --layer-name mask \
  --output clip.plan.json
```

Validation checks Workflow v1 structure and parameters. Planning records dependencies, defaults,
external inputs, terminal outputs, and declared CRS behavior without opening feature data.

## Stage 4: preflight actual inputs

```bash
starshine preflight examples/clip.workflow.json \
  --layer source=examples/data/clip-source.geojson \
  --layer mask=examples/data/clip-mask.geojson \
  --format json \
  --output clip.preflight.json
```

Preflight checks the actual collections against planner-derived geometry, CRS, and field contracts.
It does not execute the clip operation. A repository may instead request SARIF for code-scanning
integration.

## Stage 5: execute and retain evidence

```bash
starshine run examples/clip.workflow.json \
  --layer source=examples/data/clip-source.geojson \
  --layer mask=examples/data/clip-mask.geojson \
  --output-layer clipped \
  --output clipped.geojson \
  --manifest clipped.manifest.json
```

The manifest records workflow, input, step, output, package-version, and CRS evidence without copying
CLI paths or feature content.

## Domain adaptation

The same gate can be adapted without changing Starshine's core semantics:

- **parcel and zoning data:** quality-report topology and duplicates, then use explicit projected CRS
  for area metrics or overlay;
- **road and river centerlines:** quality-report line structure before length, nearest, or attribution
  work;
- **remote-sensing labels:** quality-report annotation polygons before clipping or conversion;
- **teaching and reproducibility:** retain each JSON report to show which check failed and which input
  digest was reviewed.

Domain-specific thresholds, repair rules, and acceptance decisions belong in a public project policy
or downstream system. Starshine supplies deterministic evidence rather than silently making those
decisions.
