# Declarative operator registry

Starshine keeps its bounded workflow operations in one declarative runtime registry. Each
`OperatorSpec` combines the executable adapter with the public input names, parameter validation,
JSON-compatible parameter schemas, defaults, output-CRS behavior, and a short description.

The registry is intentionally **not** a dynamic plugin loader. Workflow JSON cannot import Python
modules, provide callables, or execute arbitrary code. Only operators already reviewed and registered
in `src/starshine_geo/operator_registry.py` can run.

## Machine-readable catalog

Print the complete public catalog:

```bash
starshine operators
```

Write it to a file:

```bash
starshine operators --output operators.json
```

The output conforms to:

```text
schemas/operator-catalog-v1.schema.json
```

Python callers can request the same defensive JSON-ready value:

```python
from starshine_geo import operator_catalog

catalog = operator_catalog()
```

The public catalog contains documentation and JSON schemas, never executor objects or validator
callables. Tests compare it with `schemas/workflow-v1.schema.json`, so adding or changing an operator
requires both runtime and external contracts to stay synchronized.

## Reproject operator

`reproject` transforms every geometry to a target CRS while preserving feature order and properties.
The input collection should declare `starshine:crs`. For an otherwise valid unlabelled collection,
`source_crs` may be supplied explicitly. If both are present, they must describe the same CRS.

Workflow example:

```json
{
  "version": 1,
  "steps": [
    {
      "operation": "reproject",
      "inputs": {"input": "source"},
      "parameters": {"target_crs": "EPSG:3857"},
      "output": "projected"
    }
  ]
}
```

Run the tracked synthetic example:

```bash
starshine run examples/reproject.workflow.json \
  --layer source=examples/teaching/geographic-points.geojson \
  --output-layer projected \
  --output examples/output/projected-points.geojson
```

Direct API:

```python
from starshine_geo import reproject_features

projected = reproject_features(collection, target_crs="EPSG:3857")
```

Reprojection does not infer a suitable analysis CRS from the dataset. Selecting an appropriate CRS
remains an explicit domain decision. The operator only validates the declared choice and performs the
coordinate transformation.

## Extension contract

A new bounded operator should arrive through a public issue and include, in one reviewed change:

1. a focused public API implementation with synthetic or redistributable tests;
2. one `OperatorSpec` with named inputs and parameter validators;
3. the matching Workflow v1 JSON Schema branch;
4. stable validation diagnostics and direct/workflow tests;
5. catalog-schema and installed-wheel coverage;
6. documentation of CRS, geometry, property, and empty-result behavior.

This contract makes the registry a controlled extension point without turning workflow files into a
code-loading mechanism.
