# Declarative operator registry

Starshine keeps its bounded workflow operations in one declarative runtime registry. Each
`OperatorSpec` combines the executable adapter with the public input names, parameter validation,
JSON-compatible parameter schemas, defaults, sensitivity annotations, output-CRS behavior, and a
short description. Runtime execution and workflow planning resolve defaults from this same entry.

The registry is intentionally **not** a dynamic plugin loader. Workflow JSON cannot import Python
modules, provide callables, or execute arbitrary code. Only operators already reviewed and registered
in `src/starshine_geo/operator_registry.py` can run.

## Machine-readable catalog

Print the complete public catalog:

```bash
starshine operators
```

Write it to a file:

```bash
starshine operators --output operators.json
```

The output conforms to:

```text
schemas/operator-catalog-v1.schema.json
```

Python callers can request the same defensive JSON-ready value:

```python
from starshine_geo import operator_catalog

catalog = operator_catalog()
```

The public catalog contains documentation and JSON schemas, never executor objects or validator
callables. Each parameter also publishes a `sensitive` boolean. A sensitive value remains available
to its reviewed executor but is redacted from public workflow plans. Tests compare the catalog with
`schemas/workflow-v1.schema.json`, so adding or changing an operator requires runtime and external
contracts to stay synchronized.

## Reproject operator

`reproject` transforms every geometry to a target CRS while preserving feature order and properties.
The input collection should declare `starshine:crs`. For an otherwise valid unlabelled collection,
`source_crs` may be supplied explicitly. If both are present, they must describe the same CRS.

Workflow example:

```json
{
  "version": 1,
  "steps": [
    {
      "operation": "reproject",
      "inputs": {"input": "source"},
      "parameters": {"target_crs": "EPSG:3857"},
      "output": "projected"
    }
  ]
}
```

Run the tracked synthetic example:

```bash
starshine run examples/reproject.workflow.json \
  --layer source=examples/teaching/geographic-points.geojson \
  --output-layer projected \
  --output examples/output/projected-points.geojson
```

Direct API:

```python
from starshine_geo import reproject_features

projected = reproject_features(collection, target_crs="EPSG:3857")
```

Reprojection does not infer a suitable analysis CRS from the dataset. Selecting an appropriate CRS
remains an explicit domain decision. The operator only validates the declared choice and performs the
coordinate transformation.

## Clip operator

`clip` intersects each input feature with the union of a polygon mask collection. It requires both
collections to declare equivalent `starshine:crs` values, accepts only `Polygon` or `MultiPolygon`
mask features, preserves source property objects and retained order, and drops empty intersections.

```json
{
  "version": 1,
  "steps": [
    {
      "operation": "clip",
      "inputs": {"input": "source", "mask": "mask"},
      "parameters": {},
      "output": "clipped"
    }
  ]
}
```

The operator intentionally has no repair or implicit-reprojection parameter. Use reviewed geometry
repair outside the workflow and the explicit `reproject` step when coordinate systems differ. See
[CRS-safe clipping](CLIP.md).

## Geometry metrics operator

`geometry_metrics` preserves every feature and writes projected area and length values. It requires
an explicit projected CRS and rejects output-field collisions. The implementation lives in the
focused `metrics.py` module rather than extending topology-changing operator code. See
[projected geometry metrics](GEOMETRY_METRICS.md).

## Point-in-polygon join operator

`join_points_to_polygons` preserves every point and attaches one polygon identifier using
boundary-inclusive `covers` semantics. Both collections must declare equivalent CRS values, polygon
identifiers must be unique non-null JSON scalars, and output-field collisions are rejected.

```json
{
  "version": 1,
  "steps": [
    {
      "operation": "join_points_to_polygons",
      "inputs": {"points": "points", "polygons": "zones"},
      "parameters": {
        "polygon_id_field": "zone_id",
        "output_field": "joined_zone",
        "unmatched_value": "unassigned",
        "multiple_match": "first"
      },
      "output": "joined_points"
    }
  ]
}
```

The default `multiple_match` policy is `error`. The explicit `first` policy selects the first
covering polygon in input order and is intended only when that ordering is an intentional priority
rule. Unmatched points remain in the output. See
[deterministic point-in-polygon spatial join](SPATIAL_JOIN.md).

## Nearest-feature operator

`nearest` preserves each source feature and attaches a candidate identifier plus projected distance.
Both collections must declare equivalent projected CRS values. Candidate identifiers must be unique,
non-null JSON scalar values, and equal-distance ties are resolved by candidate input order.

```json
{
  "version": 1,
  "steps": [
    {
      "operation": "nearest",
      "inputs": {"source": "sources", "candidates": "facilities"},
      "parameters": {
        "candidate_id_field": "facility_id",
        "max_distance": 5000
      },
      "output": "nearest_facilities"
    }
  ]
}
```

The defaults are `nearest_id`, `nearest_distance`, and no distance limit. Empty candidates or
out-of-range matches produce `null` values without removing source features. The operator performs no
implicit reprojection or geometry repair. See [CRS-safe nearest-feature matching](NEAREST.md).

## Extension contract

A new bounded operator should arrive through a public issue and include, in one reviewed change:

1. a focused public API implementation with synthetic or redistributable tests;
2. one `OperatorSpec` with named inputs and parameter validators;
3. the matching Workflow v1 JSON Schema branch;
4. stable validation diagnostics and direct/workflow tests;
5. catalog-schema and installed-wheel coverage;
6. documentation of CRS, geometry, property, and empty-result behavior.

This contract makes the registry a controlled extension point without turning workflow files into a
code-loading mechanism.
