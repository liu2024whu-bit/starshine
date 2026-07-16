# Deterministic workflow explanations

Starshine can convert a validated data-free workflow plan into a review-oriented explanation without
loading GeoJSON, opening a GeoPackage, or executing a spatial operator. The explanation combines the
canonical plan with its graph digest and presents input provenance, direct dependencies,
registry-resolved parameter sources, output behavior, terminal layers, and checks that remain for
execution time.

## Python API

```python
from starshine_geo import explain_workflow, render_workflow_explanation_markdown

explanation = explain_workflow(workflow, {"source", "mask", "unused"})
markdown = render_workflow_explanation_markdown(explanation)
```

The machine-readable report conforms to:

```text
schemas/workflow-explanation-v1.schema.json
```

## Command line

Render Markdown to standard output:

```bash
starshine explain examples/plan.workflow.json \
  --layer-name source \
  --layer-name mask \
  --layer-name unused
```

Write JSON for CI, a documentation generator, or a review interface:

```bash
starshine explain examples/plan.workflow.json \
  --layer-name source \
  --layer-name mask \
  --layer-name unused \
  --format json \
  --output examples/output/plan.explanation.json
```

The output path cannot overwrite the workflow file. Invalid workflows use the same stable text or
JSON diagnostics as validation, planning, and graphing.

## What the explanation contains

- workflow, operator-catalog, plan, graph, and explanation digests;
- required and unused external layers plus produced and terminal layers;
- each step's operation summary and deterministic flag;
- named input roles and whether each layer is external or produced by an earlier step;
- direct step dependencies;
- registry-resolved parameter values and whether they were provided or defaulted;
- reviewed output-CRS behavior;
- generic execution-time checks that cannot be proven without feature data.

Sensitive registry parameters remain redacted by the planner before they enter the explanation or
its digest.

## Scope

An explanation describes intent; it does not certify the loaded data. Actual CRS equality,
projected-coordinate requirements, geometry types, property existence and uniqueness, output-field
collisions, spatial matches, distances, and empty results remain execution-time checks.

Use `starshine plan` for the complete structured preflight report, `starshine graph` for compact data
flow, `starshine explain` for a human-readable review narrative, and `starshine run --manifest` for
post-execution evidence.
