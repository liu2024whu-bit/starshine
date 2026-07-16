# Workflow graph export

Starshine can turn a validated workflow plan into a deterministic data-flow graph without reading
feature data or executing spatial operators. The graph is intended for documentation, teaching,
review interfaces, CI evidence, and future visual workflow editors.

## Python API

```python
from starshine_geo import build_workflow_graph, render_workflow_mermaid

graph = build_workflow_graph(workflow, {"source", "mask"})
mermaid = render_workflow_mermaid(graph)
```

The graph is bipartite: layer nodes connect to step nodes through named input edges, and each step
connects to its produced layer. External, produced, and terminal layers are explicit.

## Command line

```bash
starshine graph examples/plan.workflow.json \
  --layer-name source \
  --layer-name mask \
  --format mermaid
```

Use `--format json` for the schema-checked graph model and `--output` to write either representation.
The JSON form conforms to `schemas/workflow-graph-v1.schema.json` and includes workflow, plan, and
graph digests.

Graph construction reuses `plan_workflow()`. It therefore shares the canonical workflow validator,
registry defaults, dependency ordering, and public diagnostics. It does not load GeoJSON, inspect
CRS values from data, or execute operators.
