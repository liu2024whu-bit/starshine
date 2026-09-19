# CRS-safe polygon-mask overlay

Starshine provides two bounded operations that use the union of a polygon mask collection:

- `clip` keeps the portion of each input geometry inside the mask;
- `difference` keeps the portion of each input geometry outside the mask.

Both are available through the Python API and Workflow version 1. This page owns the shared
polygon-mask contract so the two operations do not grow parallel documentation.

## Python API

```python
from starshine_geo import clip_features, difference_features

inside = clip_features(source, mask)
outside = difference_features(source, mask)
```

## Workflow

Clip:

```json
{
  "version": 1,
  "steps": [
    {
      "operation": "clip",
      "inputs": {"input": "source", "mask": "mask"},
      "parameters": {},
      "output": "inside"
    }
  ]
}
```

Difference:

```json
{
  "version": 1,
  "steps": [
    {
      "operation": "difference",
      "inputs": {"input": "source", "mask": "mask"},
      "parameters": {},
      "output": "outside"
    }
  ]
}
```

The tracked clip workflow remains a compact executable example:

```bash
starshine run examples/clip.workflow.json \
  --layer source=examples/data/clip-source.geojson \
  --layer mask=examples/data/clip-mask.geojson \
  --output-layer clipped \
  --output examples/output/clipped.geojson
```

Difference uses the same `input` and `mask` bindings and the same CLI execution path; only the
registered operation and requested output layer change.

## Shared contract

- both inputs must be valid GeoJSON `FeatureCollection` objects;
- both collections must explicitly declare `starshine:crs`;
- the two CRS values must describe equivalent coordinate reference systems;
- every mask feature must be a `Polygon` or `MultiPolygon`;
- all mask features are unioned before the per-feature overlay operation;
- input properties and retained feature order are preserved;
- Starshine never reprojects, repairs, snaps, or guesses a precision grid implicitly;
- neither operation mutates or aliases caller-owned feature/property objects.

Use the explicit `reproject` operator first when layers are not already expressed in equivalent
CRS values.

## Clip semantics

Clip intersects each input geometry with the mask union.

- empty intersections are omitted;
- an empty mask produces an empty output collection with the input CRS;
- non-empty boundary-only intersections are retained, so a touching polygon may produce a line or
  point result.

The tracked example keeps the `west` and `east` features in input order, preserves their
properties, trims their geometries to the mask, drops the disjoint `outside` feature, and reports
output bounds `[5.0, 0.0, 25.0, 10.0]`.

## Difference semantics

Difference subtracts the mask union from each input geometry.

- completely erased input features are omitted;
- disjoint features are retained geometrically unchanged apart from canonical geometry
  representation;
- partially covered inputs keep only the outside portion;
- an empty mask retains all input features as independent output objects;
- retained non-empty output geometry is normalized before serialization so equivalent GEOS results
  have a stable representation for hashing and workflow evidence.

Difference deliberately does not merge mask attributes into output features. General union,
identity, symmetric-difference, and arbitrary overlay attribute-merging policies remain outside this
bounded operator.

## Public implementation boundary

The examples, tests, Workflow schema, planner-derived contracts, Preflight checks, and installed-wheel
smoke evidence use only synthetic data created for this public repository. The operations do not
depend on a private dataset, private repository, course archive, textbook/OCR material, or external
service.
