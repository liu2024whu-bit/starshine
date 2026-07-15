# CRS-safe nearest-feature matching

Starshine's `nearest` operator attaches one candidate identifier and one projected distance to every
source feature. It is available through the public Python API, Workflow version 1, the operator
catalog, workflow planning, and the installed command-line package.

## Python API

```python
from starshine_geo import nearest_features

matched = nearest_features(
    sources,
    facilities,
    candidate_id_field="facility_id",
    nearest_id_field="nearest_facility",
    distance_field="distance_m",
    max_distance=5000,
)
```

## Workflow

```json
{
  "version": 1,
  "steps": [
    {
      "operation": "nearest",
      "inputs": {"source": "sources", "candidates": "facilities"},
      "parameters": {
        "candidate_id_field": "facility_id",
        "nearest_id_field": "nearest_facility",
        "distance_field": "distance_m",
        "max_distance": 5000
      },
      "output": "nearest_facilities"
    }
  ]
}
```

Run the tracked synthetic example:

```bash
starshine run examples/nearest.workflow.json \
  --layer sources=examples/data/nearest-source.geojson \
  --layer facilities=examples/data/nearest-candidates.geojson \
  --output-layer nearest_facilities \
  --output examples/output/nearest-facilities.geojson

starshine inspect examples/output/nearest-facilities.geojson
```

The example produces two matches at distance `5.0`. The third source is farther than the inclusive
`max_distance` value of `40`, so both output fields are `null` while the source feature remains in the
result.

## Contract

- both inputs must be valid GeoJSON `FeatureCollection` objects;
- both collections must explicitly declare equivalent projected `starshine:crs` values;
- distances use the linear unit of that projected CRS;
- `candidate_id_field` must exist on every candidate and contain a unique, non-null finite JSON
  scalar;
- source properties and source feature order are preserved;
- equal-distance ties are resolved by candidate input order;
- `max_distance` is optional, inclusive, finite, and non-negative;
- an empty candidate collection produces one retained source feature per input with `null` match and
  distance fields;
- a source farther than `max_distance` is retained with `null` fields;
- the chosen output field names must differ and must not already exist on a source feature;
- no CRS transformation, geometry repair, or feature removal is hidden inside the operation.

Use `reproject` explicitly before `nearest` when inputs are not already in the same suitable projected
CRS. Coordinate-system selection remains a domain decision rather than an inferred convenience.

## Complexity and intended scale

The current implementation compares each source geometry with every candidate geometry. This
straightforward `O(source × candidates)` design keeps semantics easy to audit and is appropriate for
the repository's small reproducible examples and benchmark corpus. A future spatial-index
optimization must preserve the same tie-breaking, validation, and output contract and arrive through
a separately reviewed public issue.

## Public implementation boundary

All example coordinates, identifiers, expected distances, workflows, tests, and benchmark fixtures
were created for this public repository from Starshine's published contracts. They do not depend on
a private repository, private dataset, course archive, textbook/OCR material, or external service.
