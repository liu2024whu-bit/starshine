# Workflow input preflight

Starshine can check loaded external vector layers against the preparation rules published by the
operator registry and resolved by the canonical workflow planner. The core API receives in-memory
GeoJSON FeatureCollections; the CLI may adapt GeoJSON files or explicitly selected GeoPackage
layers before calling it. Preflight validates collections but does not execute spatial operators or
create produced layers.

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

GeoPackage inputs use an explicit three-part binding. The long and short option names are
equivalent, and formats may be mixed:

```bash
starshine preflight examples/plan.workflow.json \
  --layer source=examples/data/clip-source.geojson \
  --gpkg-layer mask study.gpkg analysis_mask
```

`NAME PATH LAYER` identifies the Workflow layer, the containing GeoPackage artifact, and the exact
vector layer. Explicit selection is required even for a single-layer package. All logical names are
validated together before feature I/O, so duplicates across GeoJSON and GeoPackage bindings fail
before either source is opened. The optional GeoPackage backend is loaded only when such a binding
is requested.

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

The output path cannot overwrite the workflow, a GeoJSON input, or a containing GeoPackage file.
Output and repository-relative SARIF path guards run before feature data is loaded.

## SARIF output

Use `--format sarif` when a repository or CI system should consume the same completed findings as
SARIF 2.1.0. SARIF conversion is implemented in a separate adapter and does not alter preflight
validation. Repository-relative file locations require an explicit root:

```bash
starshine preflight examples/plan.workflow.json \
  --layer source=examples/data/clip-source.geojson \
  --layer mask=examples/data/clip-mask.geojson \
  --format sarif \
  --sarif-root . \
  --output preflight.sarif
```

See [workflow preflight SARIF](WORKFLOW_PREFLIGHT_SARIF.md) and the tracked
[SARIF example](../examples/plan.workflow.preflight.sarif).

## Internal architecture

The public functions remain in `preflight.py`, but implementation responsibilities are isolated:

- `_preflight_model.py` defines the report version, type, and fixed execution-time limitations;
- `_preflight_findings.py` aggregates identical findings and bounded feature-index samples;
- `_preflight_checks.py` validates one collection or one contract use at a time;
- `_preflight_report.py` coordinates the canonical contract, cross-layer CRS equivalence, counts, and
  deterministic report digest;
- `_preflight_render.py` renders an already completed report;
- `preflight_sarif.py` consumes the public report contract and never imports checker internals;
- `_cli_layer_sources.py` validates file bindings, exposes source paths before I/O, and lazily adapts
  explicitly selected GeoPackage layers for the CLI.

The dependency graph is tested from source syntax. Internal Preflight modules cannot import the CLI
adapter or GeoPackage module, internal modules cannot import the public facade, and presentation
modules cannot import contracts, CRS, GeoJSON, geometry, or workflow execution. This separation
keeps file-format concerns outside the core report and prevents a second validation path.

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
