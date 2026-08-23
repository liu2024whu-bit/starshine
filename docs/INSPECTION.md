# Deterministic source inspection

Starshine provides two related read-only views of vector data. `inspect` validates one GeoJSON
`FeatureCollection` deeply and produces a deterministic structural report. `inventory` answers the
earlier question "what is in this source?" across GeoJSON and GeoPackage while deliberately
minimizing disclosure and I/O.

## Deep GeoJSON inspection

### Python API

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

Print or persist an inspection report:

```bash
starshine inspect examples/data/zones.geojson
starshine inspect examples/data/zones.geojson --output zones.inspection.json
```

The output path cannot resolve to the input file. For automation, use
`--diagnostic-format json`. Successful reports conform to
`schemas/inspection-report-v1.schema.json`.

## Privacy-aware source inventory

Use `inventory` before binding an unfamiliar vector source to a workflow:

```bash
starshine inventory source.geojson
starshine inventory project.gpkg --format json --output inventory.json
```

The default inventory reports layer names, spatial/nonspatial status, geometry type, CRS state,
field names and field types, plus feature-count status. It never reports attribute values and does
not report bounds unless explicitly requested.

GeoJSON must already be parsed to validate its FeatureCollection, so its feature count is known.
GeoPackage uses Pyogrio metadata calls and does not load feature rows by default. Drivers that cannot
provide a cheap count return `feature_count_status: unknown`; use `--force-feature-count` only when
that extra work is acceptable. Bounds are separately opt-in:

```bash
starshine inventory project.gpkg --force-feature-count --include-bounds
```

The same functionality is available through `inventory_source()`, `inventory_geojson()`, and
`inventory_geopackage()`. Machine-readable reports conform to
`schemas/source-inventory-v1.schema.json`.

## Privacy and scope

Neither inspection nor inventory copies property values into reports. `inspect` intentionally
includes exact collection bounds and a digest because it is a deep GeoJSON validation artifact;
`inventory` is the lower-disclosure discovery path and omits bounds by default. A digest can still
act as a derived identifier, while bounds can reveal geographic extent, so choose the lighter report
when sharing metadata outside the analysis environment.

All examples and tests in Starshine use synthetic public data created for this repository.
