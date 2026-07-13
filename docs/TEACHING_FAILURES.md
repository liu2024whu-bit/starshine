# Synthetic CRS and geometry failure examples

This directory contains deliberately small teaching cases built only from Starshine's public
contracts. Several files are intentionally invalid. They are examples of failures to recognize and
correct, not templates for production datasets.

All coordinates, properties, workflows, expected messages, and corrected outputs were created for
this public repository. They are not copied from a private project, course archive, textbook, OCR
material, or unpublished dataset.

## Verify every example

From an editable installation or an unpacked source distribution:

```bash
python scripts/verify_teaching_examples.py
```

The verifier executes the commands below, checks their exit codes and stable diagnostics, and runs
the corrected projected workflow in a temporary directory.

## 1. Geographic coordinates are not a linear working CRS

`geographic-points.geojson` declares `EPSG:4326`. The following workflow incorrectly asks Starshine
to use that geographic CRS as the buffer working CRS:

```bash
starshine validate \
  examples/teaching/buffer-geographic-invalid.workflow.json \
  --layer-name points \
  --diagnostic-format json
```

Expected exit code: `2`.

Stable diagnostic fields:

```json
{
  "code": "invalid_parameter",
  "path": "steps[0].parameters.work_crs",
  "operation": "buffer",
  "step_index": 0
}
```

The message contains `projected CRS with linear units`. A distance such as `1000` cannot be treated
as metres merely because it is written as a number; the working CRS must define suitable linear
units.

## 2. Corrected projected buffer

The corrected example uses synthetic coordinates in `EPSG:3857` for both the source and working CRS.
First validate the workflow:

```bash
starshine validate \
  examples/teaching/buffer-projected-valid.workflow.json \
  --layer-name points
```

Expected exit code: `0`. Expected output: `valid`.

Run it without modifying the tracked examples:

```bash
mkdir -p examples/output
starshine run \
  examples/teaching/buffer-projected-valid.workflow.json \
  --layer points=examples/teaching/projected-points.geojson \
  --output-layer buffers \
  --output examples/output/teaching-buffers.geojson

starshine inspect examples/output/teaching-buffers.geojson
```

The inspection report has these stable semantic fields:

```json
{
  "bbox": [-25.0, -25.0, 225.0, 125.0],
  "declared_crs": "EPSG:3857",
  "feature_count": 3,
  "geometry_counts": {"Polygon": 3},
  "property_fields": [
    "id",
    "starshine:buffer_distance",
    "starshine:work_crs"
  ],
  "schema_version": 1
}
```

The exact representation digest is useful within one software environment, but the teaching check
uses the semantic fields above so harmless geometry serialization differences are not mistaken for
a failed spatial operation.

The input collection itself has a fully deterministic report:

```bash
starshine inspect examples/teaching/projected-points.geojson
```

Its expected result is tracked at
`examples/teaching/projected-points.inspection.json`.

## 3. Self-intersecting polygon

The polygon in `self-intersecting-polygon.geojson` crosses itself.

```bash
starshine inspect \
  examples/teaching/self-intersecting-polygon.geojson \
  --diagnostic-format json
```

Expected exit code: `2`.

Stable message:

```text
Feature 0 has topologically invalid geometry
```

Do not silently repair an unknown invalid polygon in a production pipeline. Determine the intended
boundary, repair it with a documented method, and validate the repaired output before analysis.

## 4. Empty polygon

`empty-polygon.geojson` has a syntactically recognizable Polygon object but no coordinates.

```bash
starshine inspect \
  examples/teaching/empty-polygon.geojson \
  --diagnostic-format json
```

Expected exit code: `2`.

Stable message:

```text
Feature 0 has empty geometry
```

An empty geometry is different from an empty `FeatureCollection`. Starshine accepts a collection
with zero features and reports `bbox: null`, but every included feature must have a non-empty valid
geometry.

## 5. Malformed properties

GeoJSON Feature properties must be an object or `null`. This example intentionally uses a string:

```bash
starshine inspect \
  examples/teaching/malformed-properties.geojson \
  --diagnostic-format json
```

Expected exit code: `2`.

Stable message:

```text
Feature 0.properties must be an object or null
```

## Supported production pattern

For real work:

1. inspect and validate source collections before constructing a workflow;
2. preserve or explicitly declare the source CRS;
3. choose a projected working CRS appropriate for the study area and measurement;
4. keep invalid examples out of operational inputs;
5. retain the workflow, package version, and optional manifest used to produce each result.

The synthetic examples demonstrate public validation boundaries. They do not recommend `EPSG:3857`
for every project, and they do not replace domain-specific CRS selection or geometry-repair review.
