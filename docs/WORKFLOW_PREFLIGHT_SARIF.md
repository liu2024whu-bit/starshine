# Workflow preflight SARIF

Starshine can convert a completed Workflow Preflight v1 report to SARIF 2.1.0 so CI systems can
surface input-contract violations as reviewable findings. The conversion is isolated in
`preflight_sarif.py`; it does not reopen data, rebuild the workflow contract, execute spatial
operators, or change the path-free JSON preflight report.

## Command line

Run from the repository root and request SARIF explicitly:

```bash
starshine preflight examples/plan.workflow.json \
  --layer source=examples/data/clip-source.geojson \
  --layer mask=examples/data/clip-mask.geojson \
  --format sarif \
  --sarif-root . \
  --output preflight.sarif
```

`--sarif-root` defines the root used for `artifactLocation.uri` values. The workflow and every input
file must be contained by that root. Starshine rejects paths outside it instead of serializing
machine-specific absolute paths. Repository-relative locations let GitHub associate a result with an
input file while logical locations retain the workflow layer, step, operation, input, and field
context.

Exit codes keep the normal preflight meaning:

- `0` means the report completed without contract errors;
- `1` means SARIF was produced and one or more contract errors were found;
- `2` means workflow, argument, path, or file handling failed.

A passing report is still valid SARIF and contains an empty `results` array.

## Python API

```python
from starshine_geo import build_workflow_preflight_sarif

sarif = build_workflow_preflight_sarif(
    report,
    {
        "source": "examples/data/source.geojson",
        "mask": "examples/data/mask.geojson",
    },
    automation_id="starshine/preflight/examples/workflow.json",
)
```

Artifact URIs are explicit adapter inputs. The converter never derives them from hidden process state
or copies CLI paths into the canonical preflight report.

## Finding mapping

Each aggregated preflight finding becomes one SARIF result:

- preflight `error` and `warning` severities map to SARIF `error` and `warning` levels;
- the finding code becomes a stable `starshine.preflight.<code>` rule identifier;
- occurrence counts and sample feature indexes are retained as result properties;
- physical locations point to repository-relative input-layer files at line 1;
- logical locations retain layer, workflow step, operator input, and field context;
- a deterministic partial fingerprint is calculated from structural finding identity, never from
  property values or coordinates.

The tracked `examples/plan.workflow.preflight.sarif` file is generated from the repository's public
synthetic workflow and GeoJSON examples.

## Optional GitHub Actions upload

Starshine only produces SARIF. Uploading it is an explicit repository policy decision. A downstream
workflow can grant `security-events: write` and use GitHub's supported upload action:

```yaml
permissions:
  contents: read
  security-events: write

steps:
  - uses: actions/checkout@v6
  - run: >-
      starshine preflight examples/plan.workflow.json
      --layer source=examples/data/clip-source.geojson
      --layer mask=examples/data/clip-mask.geojson
      --format sarif
      --sarif-root .
      --output preflight.sarif
  - uses: github/codeql-action/upload-sarif@v4
    with:
      sarif_file: preflight.sarif
      category: starshine-workflow-preflight
```

Starshine's normal CI does not request code-scanning write permission and does not upload results
automatically. This keeps validation useful in local, classroom, research, and non-GitHub CI
environments without silently changing repository security settings.
