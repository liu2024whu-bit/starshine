# CRS-safe clipping

Starshine's `clip` operator intersects each input feature with the union of a polygon mask collection.
It is available through both the Python API and Workflow version 1.

## Python API

```python
from starshine_geo import clip_features

clipped = clip_features(source, mask)
```

## Workflow

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

Run the tracked synthetic example:

```bash
starshine run examples/clip.workflow.json \
  --layer source=examples/data/clip-source.geojson \
  --layer mask=examples/data/clip-mask.geojson \
  --output-layer clipped \
  --output examples/output/clipped.geojson

starshine inspect examples/output/clipped.geojson
```

The example keeps the `west` and `east` features in their original order, preserves their property
objects, trims their geometries to the mask, drops the disjoint `outside` feature, and reports the
output bounds `[5.0, 0.0, 25.0, 10.0]`.

## Contract

- both inputs must be valid GeoJSON `FeatureCollection` objects;
- both collections must explicitly declare `starshine:crs`;
- the two CRS values must describe equivalent coordinate reference systems;
- every mask feature must be a `Polygon` or `MultiPolygon`;
- all mask features are unioned before clipping;
- input properties and retained feature order are preserved;
- empty intersections are omitted;
- an empty mask collection produces an empty output collection with the input CRS;
- non-empty boundary-only intersections are retained, so a touching polygon may produce a line or
  point result;
- Starshine does not repair invalid source or mask geometry implicitly.

Clipping does not transform coordinates. Use the explicit `reproject` operator first when layers are
not already expressed in the same CRS. CRS selection and geometry-repair decisions remain visible
parts of the public workflow rather than hidden preprocessing.

## Public implementation boundary

The example coordinates, expected bounds, tests, workflow, and documentation were created for this
public repository from Starshine's published contracts. They do not depend on a private dataset,
private repository, course archive, textbook/OCR material, or external service.
