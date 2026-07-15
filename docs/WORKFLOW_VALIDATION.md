# Workflow validation

Starshine validates the complete workflow structure and operator parameters before executing the
first operator. This prevents a malformed later step from leaving a partially evaluated in-memory
workflow.

## Machine-readable schema

The public workflow version 1 contract is available at:

```text
schemas/workflow-v1.schema.json
```

The schema uses JSON Schema draft 2020-12 and defines a separate contract for each public operator.
It covers exact input names, required and optional parameters, numeric bounds, field-name rules, and
output names. Public valid and invalid examples are stored in `tests/fixtures/workflows/` and are
checked with an external JSON Schema validator in CI.

Runtime preflight additionally checks:

- referenced layer names are available in execution order;
- output names do not overwrite inputs or earlier results;
- unexpected workflow, step, input, and parameter fields are rejected;
- buffer distances are positive and finite;
- source and target CRS values are parseable and buffer working CRS values are projected;
- buffer segment counts and optional field names meet their public contracts;
- clip steps accept exactly the `input` and `mask` layer references and no parameters;
- geometry-metric steps accept one input and validated area/length output field names;
- nearest steps require `source`, `candidates`, and a non-empty `candidate_id_field`; optional
  output fields and `max_distance` are validated before data access;
- point-in-polygon join steps require `points`, `polygons`, and `polygon_id_field`; output fields,
  unmatched values, and ambiguity policies are validated before data access;
- the runtime registry and external Workflow Schema describe the same operator names, inputs, and
  parameters.

Data-dependent checks, such as clip mask geometry types, nearest candidate identifiers,
point/polygon join geometry types and ambiguity, CRS equivalence, and output-field conflicts, run
after every input collection has been validated but before an operator result is returned.

## Python diagnostics

`validate_workflow()` and `run_workflow()` raise `WorkflowValidationError` before execution when the
workflow contract fails. The exception contains a stable, JSON-ready `diagnostic` value:

```python
from starshine_geo import WorkflowValidationError, validate_workflow

try:
    validate_workflow(workflow, {"zones", "sites"})
except WorkflowValidationError as exc:
    print(exc.diagnostic.as_dict())
```

Example parameter result:

```json
{
  "code": "missing_parameter",
  "message": "missing required parameter for buffer: work_crs",
  "path": "steps[0].parameters.work_crs",
  "step_index": 0,
  "operation": "buffer"
}
```

## Validate from the CLI

Validation can run without loading feature data or executing spatial operators. Declare only the
public layer names that the workflow may reference:

```bash
starshine validate tests/fixtures/workflows/valid-buffer.json \
  --layer-name source
```

For automation and future UI adapters, request a stable JSON envelope:

```bash
starshine validate tests/fixtures/workflows/invalid-buffer-missing-work-crs.json \
  --layer-name source \
  --diagnostic-format json
```

The command exits with status `0` for a valid workflow and status `2` for a validation failure. The
CLI reuses the canonical Python validator; it does not maintain a second ruleset and does not require
private datasets.

## Operator catalog

The same reviewed runtime registry is documented through:

```bash
starshine operators
```

The output conforms to `schemas/operator-catalog-v1.schema.json`. Catalog tests compare each input
and parameter schema with `schemas/workflow-v1.schema.json`, preventing silent contract drift.


## Plan after validation

`plan_workflow()` and `starshine plan` reuse the canonical validator, then describe external and
produced layers, direct step dependencies, registry-resolved defaults, parameter sources, terminal
outputs, deterministic flags, and output-CRS behavior. Planning does not read feature data or execute
operators, so data-dependent geometry and CRS checks still occur when inputs are loaded and the
workflow runs. See `docs/WORKFLOW_PLANNING.md` and `schemas/workflow-plan-v1.schema.json`.
