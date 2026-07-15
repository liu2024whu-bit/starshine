# Deterministic workflow planning

Starshine can validate and describe a workflow without reading GeoJSON, opening a GeoPackage, or
executing any spatial operator. The planner is intended for review tools, teaching, CI preflight,
future user interfaces, and automation that needs a stable dependency graph before data is loaded.

## Python API

```python
from starshine_geo import plan_workflow

plan = plan_workflow(
    workflow,
    {"source", "mask"},
)
```

The second argument contains the external layer names that will be available when the workflow is
run. Planning validates the same Workflow version 1 structure and operator parameters used by
`run_workflow()`.

## Command line

Print a plan to standard output:

```bash
starshine plan examples/plan.workflow.json \
  --layer-name source \
  --layer-name mask
```

Write the same report to a file:

```bash
starshine plan examples/plan.workflow.json \
  --layer-name source \
  --layer-name mask \
  --output examples/output/workflow.plan.json
```

The output path cannot resolve to the workflow file. Validation failures can use the existing stable
JSON diagnostic envelope:

```bash
starshine plan invalid.workflow.json \
  --layer-name source \
  --diagnostic-format json
```

## Report contents

Workflow plan version 1 records:

- the Workflow and Operator Catalog versions and deterministic digests;
- declared, required, and unused external layer names;
- produced layers and terminal outputs;
- ordered steps and direct step dependencies;
- whether each input comes from an external layer or an earlier step;
- registry-resolved parameter values and whether each value was provided or defaulted;
- the reviewed operator summary, deterministic flag, and declared output-CRS behavior;
- a digest covering the complete report body.

The report conforms to:

```text
schemas/workflow-plan-v1.schema.json
```

`examples/plan.workflow.json` demonstrates a three-step dependency chain:

```text
source -> reproject -> projected -> clip -> clipped -> dissolve -> coverage
                                  ^
                                  |
                                mask
```

Its only terminal layer is `coverage`. The planner also exposes the default `source_crs: null` for
`reproject` and `group_field: null` for `dissolve`, because runtime execution and planning now resolve
defaults from the same declarative operator registry.

## Safety and scope

Planning is deliberately data-free. It can prove that layer names are available in execution order,
that parameters satisfy the public registry, and that outputs do not overwrite earlier layers. It
cannot prove data-dependent conditions such as:

- whether a loaded collection actually declares the expected CRS;
- whether two loaded CRS values are equivalent;
- whether a clip mask contains only Polygon or MultiPolygon geometry;
- whether a polygon identifier field exists or is unique;
- whether an overlay will produce an empty result;
- whether nearest candidates have unique identifiers, whether output fields already exist, or
  what the actual projected distances will be;
- whether point-in-polygon inputs use supported geometry types, whether polygon identifiers are
  unique, or whether a point will match zero, one, or multiple polygons.

- whether geometry-metric output fields collide with loaded properties or the loaded CRS is
  projected.

Those checks remain part of input validation and operator execution.

For a `join_points_to_polygons` step, the planner resolves `output_field` to `polygon_id`,
`unmatched_value` to `null`, and `multiple_match` to `error` unless supplied. It cannot decide actual
matches without loading geometries.

For a `nearest` step, the planner resolves `distance_field` to `nearest_distance`,
`nearest_id_field` to `nearest_id`, and `max_distance` to `null` unless the workflow supplies other
values. These defaults are the same values used by execution.

The plan contains resolved parameter values. Parameters marked `sensitive` in the reviewed registry
are replaced with `<redacted>` before they enter a public plan or its digest. Current built-in
operators do not define sensitive parameters, but the annotation establishes a safe boundary for
future adapters.

A plan is not an execution manifest. It describes intended structure before data is loaded; the
optional reproducibility manifest records the workflow and content digests after a selected result
has been produced.
