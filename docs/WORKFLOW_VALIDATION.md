# Workflow validation

Starshine validates the complete workflow structure before executing the first operator. This prevents a later malformed step from leaving a partially evaluated in-memory workflow.

## Machine-readable schema

The public workflow version 1 contract is available at:

```text
schemas/workflow-v1.schema.json
```

The schema documents the supported operations, required step fields, input references, optional parameters object, and output name. Runtime validation additionally checks layer availability and prevents output names from overwriting existing or earlier workflow layers.

## Structured diagnostics

`validate_workflow()` and `run_workflow()` raise `WorkflowValidationError` for structural failures. The exception contains a `diagnostic` value with stable fields:

```python
from starshine_geo import WorkflowValidationError, validate_workflow

try:
    validate_workflow(workflow, {"zones", "sites"})
except WorkflowValidationError as exc:
    print(exc.diagnostic.as_dict())
```

Example result:

```json
{
  "code": "unknown_input_layer",
  "message": "unknown input layer: missing",
  "path": "steps[0].inputs.polygons",
  "step_index": 0,
  "operation": "summarize_points_within"
}
```

The dictionary format is intended for command-line adapters, future user interfaces, test assertions, and API error envelopes. Operator-specific data and parameter checks remain owned by the operators themselves.
