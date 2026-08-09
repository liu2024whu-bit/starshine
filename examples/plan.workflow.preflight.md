# Starshine Workflow Input Preflight

- Status: **PASS**
- Checked layers: 2 / 3
- Errors: 0
- Warnings: 1

## Layer `mask`

- Status: passed
- Required: yes
- Declared CRS: `"EPSG:3857"`
- Features: 1
- Geometry: `Polygon` × 1
- Findings:
  - **WARNING** `deferred_crs_equivalence` (step 1, input `mask`): CRS equivalence depends on a layer produced by an earlier workflow step. Count: 1

## Layer `source`

- Status: passed
- Required: yes
- Declared CRS: `"EPSG:3857"`
- Features: 3
- Geometry: `Polygon` × 3
- Findings: none

## Layer `unused`

- Status: skipped
- Required: no
- Declared CRS: `"EPSG:3857"`
- Findings: none

## Remaining execution-time checks

- CRS equivalence involving a layer produced by an earlier step remains deferred to execution.
- Produced-layer geometry and property contracts can only be checked after their producer runs.
- Spatial relationships, distances, ambiguity outcomes, and empty results require operator execution.
- Output feature counts and post-execution manifest digests require running the workflow.

## Evidence

- Workflow digest: `sha256:ce8caa2b82cb5c54059f4b48db3763620c3ced37263081ad457252121dff66ef`
- Contract digest: `sha256:31f2803237bab6958882475d00ebf7a81048cb22593670c7c217a41a301d0737`
- Preflight digest: `sha256:85787dbfd5d39dfa9118970232c7a482a3e09240f3c13c59d49cf44ea43fcf42`
