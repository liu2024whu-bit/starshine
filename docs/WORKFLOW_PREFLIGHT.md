# Workflow input preflight

Starshine can check loaded external GeoJSON layers against the preparation rules published by the
operator registry and resolved by the canonical workflow planner. Preflight reads and validates
input collections, but it does not execute spatial operators or create produced layers.

## Python API

```python
from starshine_geo import preflight_workflow_inputs

report = preflight_workflow_inputs(
    workflow,
    {
        "source": source_collection,
        "mask": mask_collection,
    },
)
```

The report conforms to `schemas/workflow-preflight-v1.schema.json` and records deterministic
Workflow, Operator Catalog, Plan, Contract, collection, and preflight digests without copying feature
coordinates or property values into findings.

## Command line

```bash
starshine preflight examples/plan.workflow.json \
  --layer source=examples/data/clip-source.geojson \
  --layer mask=examples/data/clip-mask.geojson
```

Markdown is the default output. Use JSON for CI or another interface:

```bash
starshine preflight examples/plan.workflow.json \
  --layer source=examples/data/clip-source.geojson \
  --layer mask=examples/data/clip-mask.geojson \
  --format json \
  --output examples/output/plan.preflight.json
```

The command exits with:

- `0` when the preflight completes without errors;
- `1` when the report is produced but one or more input-contract checks fail;
- `2` for workflow, file, argument, or other Starshine errors.

The output path cannot overwrite the workflow or any input layer.

## Checks

Preflight currently checks:

- GeoJSON `FeatureCollection`, feature, geometry validity, and JSON serializability;
- allowed geometry types for each external input use;
- declared CRS presence and parseability;
- projected-CRS requirements;
- agreement between declared CRS values and explicit CRS parameters;
- equivalent CRS requirements when both related inputs are external layers;
- required property fields;
- non-null, unique, and finite-JSON-scalar field constraints;
- operator output fields that would collide with existing properties;
- multiple output parameters that resolve to the same field name.

Repeated feature-level failures are aggregated by rule. Reports contain occurrence counts and up to
20 sample feature indexes, not the failing property values.

## Deliberate boundary

Preflight is stricter than a static contract because it inspects loaded collections, but it is still
not workflow execution. A CRS relationship involving a layer produced by an earlier step is reported
as deferred. Spatial relationships, actual distances, multiple-match outcomes, empty outputs, and
result counts remain execution-time facts.

Use the workflow tools in this order when appropriate:

1. `validate` for Workflow v1 structure and parameters;
2. `plan` for dependencies and resolved defaults;
3. `contract` for a data-preparation checklist;
4. `preflight` for actual external-layer conformance;
5. `run` for spatial execution;
6. `--manifest` for post-execution reproducibility evidence.

The tracked `examples/plan.workflow.preflight.md` report is generated exclusively from public
synthetic data in this repository.
