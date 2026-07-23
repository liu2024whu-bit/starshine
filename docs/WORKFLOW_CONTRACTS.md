# Workflow input contracts

Starshine can turn a validated workflow into a deterministic preparation checklist for every declared external layer. Contract generation is data-free: it does not open GeoJSON, read a GeoPackage, or execute a spatial operator.

The report combines two existing public sources of truth:

- `plan_workflow()` provides validated step order, resolved defaults, redaction, and layer provenance;
- each registered `InputSpec` provides declarative geometry, CRS, field-read, and field-write rules.

This keeps operator execution and preparation guidance synchronized without adding a second validation engine.

## Python API

```python
from starshine_geo import build_workflow_contract, render_workflow_contract_markdown

contract = build_workflow_contract(
    workflow,
    {"source", "mask", "unused"},
)
markdown = render_workflow_contract_markdown(contract)
```

## Command line

Render a Markdown checklist:

```bash
starshine contract examples/plan.workflow.json \
  --layer-name source \
  --layer-name mask \
  --layer-name unused
```

Write machine-readable JSON:

```bash
starshine contract examples/plan.workflow.json \
  --layer-name source \
  --layer-name mask \
  --layer-name unused \
  --format json \
  --output examples/output/plan.contract.json
```

The JSON report conforms to `schemas/workflow-contract-v1.schema.json`. A tracked Markdown rendering is available at `examples/plan.workflow.contract.md`.

## What the report describes

For each external layer and each workflow use, the contract records:

- allowed geometry types, or that any validated GeoJSON geometry is accepted;
- whether CRS metadata is unnecessary, declared, projected, parameter-driven, or must equal another input;
- required property fields and uniqueness, nullability, or finite-scalar rules;
- fields written by the operator and whether collisions are rejected or overwritten;
- operator-specific notes where the current runtime intentionally accepts missing fields or does not enforce a broader semantic assumption.

Unused declared layers remain visible with zero uses.

## Scope

A contract is a preparation checklist, not proof that loaded data conforms. Actual geometry types, CRS equivalence, property values, collisions, spatial relationships, distances, and output counts remain execution-time checks. Use `starshine inspect` for one loaded collection and `starshine run --manifest` for post-execution evidence.
