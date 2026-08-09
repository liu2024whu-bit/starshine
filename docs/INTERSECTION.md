# Deterministic pairwise intersection overlay

`intersect_features()` performs an exact pairwise overlay between two validated vector
FeatureCollections. It is intended for workflows where the identity of the intersecting right-side
feature matters, such as parcel/zoning overlays, habitat/management zones, road/protection-area
crossings, catchment attribution, and vector-label preparation.

The operation is deliberately narrower than a general GIS overlay framework. It emits one feature
for every **non-empty left/right geometry intersection** and keeps the provenance rule explicit:
left properties are copied and one unique right-side identifier is written to a configured output
field.

## Python API

```python
from starshine_geo import intersect_features

result = intersect_features(
    parcels,
    planning_zones,
    right_id_field="zone_id",
    output_field="planning_zone",
)
```

Both inputs must be valid GeoJSON FeatureCollections with equivalent declared `starshine:crs`
values. Starshine does not infer or transform a CRS for this operation.

## Workflow operation

```json
{
  "version": 1,
  "steps": [
    {
      "operation": "intersection",
      "inputs": {
        "left": "parcels",
        "right": "zones"
      },
      "parameters": {
        "right_id_field": "zone_id",
        "output_field": "planning_zone"
      },
      "output": "parcel_zone_intersections"
    }
  ]
}
```

Run the tracked synthetic example:

```bash
starshine run examples/intersection.workflow.json \
  --layer parcels=examples/data/intersection-parcels.geojson \
  --layer zones=examples/data/intersection-zones.geojson \
  --output-layer parcel_zone_intersections \
  --output examples/output/parcel-zone-intersections.geojson
```

## Exact output contract

For each left feature, Starshine queries intersecting right candidates through the deterministic
STRtree boundary and then evaluates the exact geometry intersection. Results are emitted in:

```text
left input order → right input order
```

STRtree traversal order is never exposed.

Every emitted feature:

- contains the strict-normal-form intersection geometry;
- copies the left feature properties into a new object;
- adds the matched right identifier under `output_field`;
- retains the left collection CRS declaration.

The right identifier field must contain unique, non-null, finite JSON scalar values. The configured
output field must not already exist on any left feature.

## Boundary intersections are data

A non-empty intersection is retained even when its dimension is lower than either source geometry.
For example, two polygons that only share an edge produce a `LineString`, while corner-only contact
can produce a `Point`.

Starshine does **not** silently discard those results because dimensional filtering is a domain
choice. A cadastral area-only workflow may decide to remove zero-area intersections later, while a
network or boundary-audit workflow may specifically need them.

## Determinism and canonical geometry

GEOS constructive operations can return geometrically equivalent results with coordinate or
collection ordering that should not be treated as application semantics. Starshine normalizes every
non-empty result to Shapely strict canonical form before GeoJSON serialization. Shapely documents
strict normalization as the stable canonical representation intended for structural comparison.

This does not repair geometry, snap coordinates, or introduce a precision grid.

## Failure behavior

- invalid or empty source geometries fail through normal FeatureCollection validation;
- missing, duplicate, null, non-finite, or non-scalar right identifiers fail before overlay output;
- CRS mismatch fails before candidate discovery;
- an exact GEOS intersection failure identifies both left and right feature indexes;
- expected GEOS failures during indexed candidate discovery fall back to exact exhaustive predicate
  evaluation with stable pair diagnostics;
- unrelated programming exceptions are not converted into data-validation errors.

Inputs are not mutated.

## Performance boundary

Candidate discovery uses one immutable STRtree built from the right geometry sequence for the whole
operation. The tree filters pair candidates with the exact `intersects` predicate, after which the
constructive `intersection` operation is executed only for retained pairs.

The public benchmark corpus includes a 1,600-parcel by 400-zone case. The focused spatial-index report
runs both the indexed public API and an independent exhaustive reference, requires equal semantic
digests, and records timing as environment-specific evidence rather than a CI pass/fail threshold.

## Deliberate limits

This operation does not provide:

- union, erase/difference, identity, or symmetric-difference overlays;
- automatic attribute merging from the right collection beyond one explicit identifier;
- area-only or dimension-only filtering;
- snapping, tolerances, geometry repair, or precision-grid changes;
- automatic or hidden reprojection;
- approximate spatial queries or global index caching.

Those behaviors need separate contracts because each changes analytical meaning.
