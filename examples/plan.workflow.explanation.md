# Starshine Workflow Explanation

- Workflow version: `1`
- Steps: 3
- Required external layers: `mask`, `source`
- Unused external layers: `unused`
- Terminal layers: `coverage`
- All steps deterministic: yes

## Step 0: `reproject`

Transform every geometry to a target CRS while preserving properties and order.

### Inputs

- `input`: external layer `source`

### Parameters

- `target_crs` = `"EPSG:3857"` (provided)
- `source_crs` = `null` (default)

- Direct dependencies: none
- Output layer: `projected`
- Output CRS behavior: target_crs parameter
- Deterministic: yes
- Terminal output: no

## Step 1: `clip`

Intersect each input feature with the union of a polygon mask collection.

### Inputs

- `input`: layer `projected` produced by step 0
- `mask`: external layer `mask`

### Parameters

- none

- Direct dependencies: 0
- Output layer: `clipped`
- Output CRS behavior: input layer; mask must declare an equivalent CRS
- Deterministic: yes
- Terminal output: no

## Step 2: `dissolve`

Union all input geometries, optionally grouped by one property field.

### Inputs

- `input`: layer `clipped` produced by step 1

### Parameters

- `group_field` = `null` (default)

- Direct dependencies: 1
- Output layer: `coverage`
- Output CRS behavior: input layer
- Deterministic: yes
- Terminal output: yes

## Remaining execution-time checks

- Loaded collections must satisfy their declared CRS and geometry contracts.
- Required properties, identifier uniqueness, and output-field collisions are checked with data.
- Spatial relationships, distances, and empty-result behavior depend on actual feature content.
- Post-execution output and manifest digests require running the workflow.

## Evidence

- Workflow digest: `sha256:ce8caa2b82cb5c54059f4b48db3763620c3ced37263081ad457252121dff66ef`
- Plan digest: `sha256:515d855bf7acfdd88ad9ec71909a60d552c8dfd051f2a2ce038c5d6f68e66339`
- Graph digest: `sha256:cbf41366749f7adb962f64ac0b4e205ff018818f66a73e5234b18e411388e664`
- Explanation digest: `sha256:c1123630ca5c8d9bfb6199a4fb3b7ee74eaaf2b52a68b8faac14b95692806e24`
