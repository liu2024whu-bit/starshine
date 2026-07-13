# Deterministic GeoJSON inspection

Starshine can validate one GeoJSON `FeatureCollection` and produce a small, deterministic report
without running a workflow or copying feature content into the report.

## Python API

```python
from starshine_geo import inspect_feature_collection

report = inspect_feature_collection(collection)
```

The report includes:

- `feature_count`;
- counts by GeoJSON geometry type;
- the sorted union of property field names;
- the declared `starshine:crs`, when present;
- collection bounds as `[min_x, min_y, max_x, max_y]`;
- a SHA-256 digest of the validated collection;
- `schema_version`, currently `1`.

An empty but valid collection has empty geometry and property summaries and returns `bbox: null`.
The inspector validates every geometry first, so malformed or topologically invalid features fail
instead of producing a misleading partial report.

## Command line

Print a report to standard output:

```bash
starshine inspect examples/data/zones.geojson
```

Write the report to a file:

```bash
starshine inspect examples/data/zones.geojson \
  --output zones.inspection.json
```

The output path cannot resolve to the input file, so inspection cannot replace the source GeoJSON.

For automation, request a JSON error envelope when validation fails:

```bash
starshine inspect invalid.geojson --diagnostic-format json
```

Successful reports conform to:

```text
schemas/inspection-report-v1.schema.json
```

## Privacy and scope

Inspection reports contain structural metadata and a digest, not feature coordinates or property
values. The digest can still be used to test whether two exact collection representations match, so
reports should be shared according to the same data-governance rules as other derived identifiers.
All examples and tests in Starshine use synthetic public data created for this repository.
