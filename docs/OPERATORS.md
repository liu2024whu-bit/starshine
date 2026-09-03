# Declarative operator registry

Starshine keeps its bounded workflow operations in one declarative runtime registry. Each
`OperatorSpec` combines the executable adapter with the public input names, parameter validation,
JSON-compatible parameter schemas, defaults, sensitivity annotations, per-input data contracts,
output-CRS behavior, and a short description. Runtime execution and workflow planning resolve
defaults from this same entry.

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
callables. Each parameter also publishes a `sensitive` boolean. A sensitive value remains available
to its reviewed executor but is redacted from public workflow plans. Tests compare the catalog with
`schemas/workflow-v1.schema.json`, so adding or changing an operator requires runtime and external
contracts to stay synchronized.

## Reviewed operator map

This page owns the registry, catalog, and extension model. It intentionally does not duplicate the
full contract of an operator that already has a focused reference page.

| Operator | Role | Human contract owner |
| --- | --- | --- |
| `buffer` | projected-distance buffering with explicit CRS choices | catalog and Workflow schema |
| `clip` | CRS-safe clipping against polygon masks | [CLIP.md](CLIP.md) |
| `dissolve` | deterministic grouping and geometry union | catalog and Workflow schema |
| `geometry_metrics` | projected area and length fields | [GEOMETRY_METRICS.md](GEOMETRY_METRICS.md) |
| `intersection` | deterministic pairwise overlay | [INTERSECTION.md](INTERSECTION.md) |
| `join_points_to_polygons` | boundary-inclusive point attribution | [SPATIAL_JOIN.md](SPATIAL_JOIN.md) |
| `nearest` | projected nearest-feature attribution and distance | [NEAREST.md](NEAREST.md) |
| `reproject` | explicit coordinate transformation | this page, below |
| `summarize_points_within` | grouped point counts within polygons | catalog and Workflow schema |

For operators without a dedicated page, the machine-readable catalog and Workflow schema remain the
public parameter contract rather than creating another Markdown page solely to mirror those values.
The root README and tracked synthetic examples provide the normal usage entry points.

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
code-loading mechanism. A dedicated operator page is warranted only when it owns meaningful
human-facing semantics that cannot be stated clearly by the catalog, schema, examples, and an
existing conceptual document.

## Input contract metadata

Every catalog input publishes a `contract` object describing geometry restrictions, CRS rules,
parameter-named required fields, fields written by the operator, collision policy, and focused notes.
`build_workflow_contract()` resolves this metadata with planner defaults and external-layer
provenance. See [workflow input contracts](WORKFLOW_CONTRACTS.md).
