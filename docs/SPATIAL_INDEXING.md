# Deterministic spatial indexing

Starshine uses one immutable Shapely `STRtree` per validated candidate collection to accelerate the
public nearest-feature, point-in-polygon, and pairwise-intersection operators. The index changes how candidate geometries
are located; it does not change any public spatial meaning.

## Why a wrapper is required

An STRtree is a query-only index over two-dimensional axis-aligned geometry envelopes. Query methods
return indices into the geometry sequence used to construct the tree. That is useful for Starshine
because identifiers and other reviewed records can remain in separate arrays with the same input
order.

The raw result order is not a public contract. In particular:

- a single-result nearest query may choose one equidistant geometry according to internal traversal
  order;
- all-match nearest and predicate queries may return tree indices in no meaningful order;
- Z coordinates are ignored by the index and by the existing planar distance/topology operations.

Starshine therefore never exposes STRtree traversal order. The internal wrapper requests every exact
nearest tie, compares returned distances, and resolves ties by the smallest original candidate index.
Point-in-polygon matches are sorted by original polygon index before the existing `first` or `error`
policy is applied.

## Dependency boundary

The implementation follows one direction:

`operators.py → _spatial_index.py → Shapely STRtree`

`operators.py` continues to own:

- FeatureCollection validation;
- CRS requirements;
- identifier and output-field rules;
- source-order and property preservation;
- public error and ambiguity policies;
- final FeatureCollection assembly.

`_spatial_index.py` owns only:

- one immutable geometry sequence and STRtree per operation;
- deterministic nearest-index selection;
- sorted point-in-polygon candidate indices;
- a bounded exhaustive fallback if GEOS rejects an indexed query.

The index module does not import Workflow, the operator registry, Preflight, CLI, GeoPackage, SARIF,
manifests, planning, or public facades. AST tests enforce this boundary.

## Nearest-feature query

The public nearest contract remains:

1. validate both collections and equivalent projected CRS values;
2. validate unique candidate identifiers and source output fields;
3. construct one tree from candidate geometries;
4. query all exact nearest matches for each source geometry;
5. choose the smallest distance and then the smallest candidate input index;
6. apply the inclusive `max_distance` rule and emit explicit null fields when no match qualifies.

A zero distance limit remains valid in Starshine. Because the underlying STRtree query accepts only a
strictly positive query limit, zero is applied after the exact nearest distance is returned.

## Point-in-polygon query

The tree stores polygon geometries and the query geometry is a point. Shapely evaluates a query
predicate in the orientation `predicate(input_geometry, tree_geometry)`, so Starshine uses
`covered_by(point, polygon)`, which is the inverse orientation of the public
`polygon.covers(point)` rule. Boundary points therefore remain included.

Returned polygon indices are de-duplicated and sorted. The public policy then remains:

- no indices: retain the point with `unmatched_value`;
- one index: attach that polygon identifier;
- several indices with `multiple_match="first"`: select the earliest polygon input;
- several indices with `multiple_match="error"`: raise the existing ambiguity error.


## Pairwise intersection candidate query

The tree stores right-side geometries and each left geometry is queried with the exact `intersects`
predicate. Returned indices are de-duplicated and sorted to original right input order before the
constructive intersection runs. The index only decides which right geometries are candidates; exact
intersection geometry, canonical normalization, left-property copying, identifier provenance, and
empty-result filtering remain operator responsibilities.

A GEOS failure in candidate discovery falls back to exhaustive `intersects` predicate evaluation.
A failure in the constructive intersection itself is not retried through another algorithm and
reports the stable left/right feature indexes.

## Failure behavior

Only expected `GEOSException` failures from an indexed query trigger the exhaustive reference path.
That path evaluates candidates in original order and retains the established feature-index
information in validation errors. Unexpected exceptions are not converted to data findings and
remain visible to developers.

The fallback is a correctness and diagnostic boundary, not a second normal execution engine.

## Differential evidence

Tests compare indexed public results with independent exhaustive implementations across:

- generated nearest grids and exact ties;
- zero, inclusive, restrictive, and absent distance limits;
- point interiors, shared boundaries, overlapping polygons, and unmatched points;
- reversed and duplicated mocked STRtree result order;
- expected GEOS fallback and unexpected programming errors;
- input non-mutation and one-tree-per-operation construction.

The public benchmark corpus version 7 includes three focused indexed scale cases:

- `intersection-index-parcels-1600-zones-400`;
- `join-index-points-1024-zones-256`;
- `nearest-index-grid-900-candidates-225`.

The focused comparison report runs both the indexed public API and an independent exhaustive
reference and requires equal semantic digests:

```bash
python -m benchmarks.spatial_index --repeat 5 --output spatial-index-report.json
python scripts/check_spatial_index_benchmark.py spatial-index-report.json
```

It records environment metadata, source/candidate counts, exhaustive pair counts, both timing
series, and the observed speedup. Timing is evidence, not a shared-runner pass/fail threshold.
Semantic equality is mandatory.

## Limits

- This is an exact index, not approximate nearest-neighbor search.
- Bounding-box overlap can still produce many candidates for large or widely separated
  MultiPolygons.
- Indexing does not select a CRS or make geographic coordinates suitable for distance measurement.
- No mutable global cache is retained between calls.
- No tolerance, snapping, precision grid, repair, or hidden reprojection is introduced.
