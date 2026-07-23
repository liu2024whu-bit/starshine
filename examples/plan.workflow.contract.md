# Starshine Workflow Input Contract

- Workflow version: `1`
- Declared external layers: 3
- Required external layers: 2
- Unused external layers: 1

## Layer `mask`

Used by 1 workflow input(s).

### Step 1: `clip` / `mask`

- Geometry: `Polygon`, `MultiPolygon`
- CRS: must declare `starshine:crs`; CRS must equal layer `projected`
- Required fields: none
- Fields written by the operator: none

## Layer `source`

Used by 1 workflow input(s).

### Step 0: `reproject` / `input`

- Geometry: any validated GeoJSON geometry type
- CRS: must declare `starshine:crs`
- Required fields: none
- Fields written by the operator: none

## Layer `unused`

This declared layer is not referenced by the workflow.

## Remaining execution-time checks

- Feature geometry types and property values must be checked against each listed input use.
- Declared CRS values, CRS equivalence, and projected-coordinate requirements need loaded data.
- Field uniqueness, nullability, scalar constraints, and collision policies need loaded properties.
- Spatial relationships, distances, and output feature counts remain execution-time results.

## Evidence

- Workflow digest: `sha256:ce8caa2b82cb5c54059f4b48db3763620c3ced37263081ad457252121dff66ef`
- Plan digest: `sha256:515d855bf7acfdd88ad9ec71909a60d552c8dfd051f2a2ce038c5d6f68e66339`
- Contract digest: `sha256:026e690156bea9f63c46dc6bea64cd412184d669e8acc28f12d7b818e0089fbe`
