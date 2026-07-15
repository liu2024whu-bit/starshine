# Deterministic point-in-polygon spatial join

Starshine's `join_points_to_polygons` operator attaches one polygon identifier to every point while
preserving the point collection as the primary output. It is available through the Python API,
Workflow version 1, the operator catalog, data-free planning, benchmarks, and the installed CLI.

## Python API

```python
from starshine_geo import join_points_to_polygons

joined = join_points_to_polygons(
    points,
    zones,
    polygon_id_field="zone_id",
    output_field="joined_zone",
    unmatched_value="unassigned",
    multiple_match="first",
)
```

## Workflow

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

Run the tracked synthetic example:

```bash
starshine run examples/spatial-join.workflow.json \
  --layer points=examples/data/join-points.geojson \
  --layer zones=examples/data/join-polygons.geojson \
  --output-layer joined_points \
  --output examples/output/joined-points.geojson

starshine inspect examples/output/joined-points.geojson
```

The example contains an interior point in each zone, one point on the shared polygon boundary, and
one unmatched point. It opts into `multiple_match: first`, so the boundary point receives the first
covering polygon identifier (`west`). The outside point is retained with `joined_zone: unassigned`.

## Contract

- both inputs must be valid GeoJSON `FeatureCollection` objects;
- both collections must explicitly declare equivalent `starshine:crs` values;
- the source collection must contain only `Point` geometry;
- the join collection must contain only `Polygon` or `MultiPolygon` geometry;
- polygon matching uses boundary-inclusive `covers` semantics;
- `polygon_id_field` must exist on every polygon and contain a unique, non-null finite JSON scalar;
- point properties, geometry, and input order are preserved;
- unmatched points remain in the output and receive `unmatched_value`;
- `unmatched_value` must be a finite JSON scalar or `null`;
- the output field must not already exist on any point;
- `multiple_match: error` is the default and rejects ambiguous overlapping or shared-boundary
  matches;
- `multiple_match: first` is an explicit deterministic alternative that selects the first covering
  polygon in input order;
- no reprojection, geometry repair, aggregation, or feature removal is hidden inside the operator.

Because this is a topological containment operation rather than a measurement operation, an
equivalent geographic CRS is accepted. The coordinates must still describe the same CRS in both
collections. Use `reproject` explicitly when they do not.

## Why ambiguity fails by default

A boundary point may be covered by two adjacent polygons, and overlapping polygons may cover the same
interior point. Silently selecting one changes attribution semantics. Starshine therefore fails by
default and requires the workflow author to opt into the deterministic `first` policy when input
order is an intentional priority rule.

## Complexity and intended scale

The initial implementation checks every point against every polygon. This transparent
`O(points × polygons)` behavior is appropriate for the small auditable workflows and benchmark
corpus. A future spatial-index optimization must preserve boundary, ordering, ambiguity, validation,
and output contracts.

## Public implementation boundary

All geometries, identifiers, expected assignments, workflows, tests, and benchmark fixtures were
created for this public repository from Starshine's published contracts. They do not depend on a
private repository, private dataset, course archive, textbook/OCR material, or external service.
