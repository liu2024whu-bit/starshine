# Geometry quality reports

Starshine Geometry Quality is a read-only diagnostic surface for GeoJSON `FeatureCollection` data.
It is designed for GIS preparation, teaching, reproducible review, and CI checks where invalid or
suspicious geometry must be described before a workflow is allowed to fail during execution.

The quality assessor does **not** repair geometry, remove duplicates, select a CRS, reproject
coordinates, mutate properties, or execute a workflow operator.

## Command line

```bash
starshine quality examples/geometry-quality.geojson
```

Markdown is the default output. Request the schema-checked JSON report for CI or another interface:

```bash
starshine quality examples/geometry-quality.geojson \
  --format json \
  --output geometry-quality.report.json
```

The command exits with:

- `0` when the report contains no error-level geometry findings; warnings may still be present;
- `1` when a report is produced with one or more error-level findings, including non-finite or other
  non-JSON in-memory values that make the canonical collection digest unavailable;
- `2` when the source cannot be read, the top-level JSON structure is not a FeatureCollection, or
  command arguments are invalid.

The output path cannot overwrite the source GeoJSON file.

## Python API

```python
from starshine_geo import assess_geometry_quality, render_geometry_quality_markdown

report = assess_geometry_quality(collection)
markdown = render_geometry_quality_markdown(report)
```

The report conforms to
[`schemas/geometry-quality-report-v1.schema.json`](../schemas/geometry-quality-report-v1.schema.json).
The tracked synthetic example includes the source collection, canonical JSON report, and Markdown
rendering:

- [`examples/geometry-quality.geojson`](../examples/geometry-quality.geojson)
- [`examples/geometry-quality.report.json`](../examples/geometry-quality.report.json)
- [`examples/geometry-quality.report.md`](../examples/geometry-quality.report.md)

## Internal responsibility boundary

The public `geometry_quality.py` module is a small facade. Coordinate inspection, finding
aggregation, report assembly, and Markdown rendering live in separate internal modules with an
acyclic import graph enforced by source-level tests. Geometry Quality does not import Workflow,
operators, Preflight, or GeoPackage code. This separation keeps future format adapters and
domain-specific quality policies from competing with the generic report builder.

## What is checked

The current version reports:

- entries that are not GeoJSON Features;
- missing or unparseable geometry objects;
- malformed coordinate arrays, non-finite ordinates, and unsupported coordinate dimensions;
- empty geometries;
- topologically invalid geometries with coordinate-free validity reasons;
- mixed two- and three-dimensional coordinate positions;
- exact duplicate normalized geometries;
- missing or unparseable `starshine:crs` metadata;
- geometry-type, coordinate-dimension, coordinate-count, duplicate-group, and validity totals.

An invalid feature may contribute more than one finding. `invalid_geometry_count` counts unique feature
indexes with at least one error, while `error_count` and `warning_count` count finding occurrences.

## Professional GIS use cases

The report is intentionally generic enough to support several real preparation stages without
embedding domain-specific repair rules:

- **cadastral and planning polygons:** expose self-intersections, empty parcels, duplicate boundaries,
  and missing CRS metadata before area, overlay, or legal-boundary review;
- **road and river centerlines:** identify unparseable or empty linework, mixed coordinate dimensions,
  and exact duplicate segments before network construction or length measurement;
- **contours and digitized thematic layers:** summarize geometry types and coordinate complexity before
  clipping, reprojection, or cartographic generalization;
- **remote-sensing vector labels:** detect invalid or duplicated annotation geometry before training,
  evaluation, or conversion to another labeling format.

These examples describe where the diagnostics are useful, not automatic acceptance criteria.
Project-specific tolerances and repair decisions remain outside the generic report.

## Duplicate definition

Duplicate detection is intentionally narrow and deterministic. It is applied only to successfully
parsed, non-empty, topologically valid geometries. Starshine normalizes each geometry and groups equal
normalized WKB representations written with an explicit byte order and output dimension. The WKB
bytes are used only as in-memory grouping keys and are never copied into the report.

A duplicate warning is not an instruction to delete data. Coincident features may be correct in
multi-theme, temporal, legal, or source-provenance datasets. The report exposes the condition for
review and leaves the decision to the user.

## Privacy and evidence

Reports do not copy:

- feature properties or identifiers;
- coordinate arrays;
- validity-location coordinates;
- geometry WKB or per-feature geometry digests;
- file paths;
- arbitrary invalid geometry-type or CRS strings.

Findings contain stable codes, aggregate occurrence counts, safe geometry-type labels, and up to 20
unique feature-index samples. For JSON-compatible input, the collection digest identifies the
canonicalized JSON value rather than source-file bytes or key order. If the in-memory value contains
non-JSON data such as a non-finite number, `collection_digest` is `null`,
`collection_digest_status` is `unavailable`, and the report records an error without copying the value.
The quality digest always covers the complete, JSON-safe report body.

## Deliberate limits

Geometry Quality is not a replacement for Workflow Preflight or operator execution:

- it does not know an operator's expected geometry type, field contract, or CRS relationship;
- it does not test spatial relationships between layers;
- it does not calculate domain-specific tolerances such as minimum parcel area, road snap distance,
  or contour interval;
- it does not perform automatic `make_valid`, buffering, simplification, snapping, or deduplication;
- it does not infer whether geographic or projected coordinates are appropriate for a later task.

Use `quality` for collection-level geometry diagnostics, `preflight` for planner-derived workflow input
contracts, and `run` for the actual spatial operation.
