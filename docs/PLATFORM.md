# Platform architecture

Starshine's platform layer sits **above** the existing geospatial core. It does not replace the CLI,
operator registry, Workflow model, Preflight checks, or spatial operators.

The dependency direction is one way:

`Web client → Starshine Server → public starshine_geo API → workflow/runtime core`

The core package must never import the server or browser layers.

## 0.8A: read-only API foundation

The first platform increment deliberately exposes only data-free review surfaces:

- `GET /healthz` — service/API/core version health;
- `GET /api/v1/operators` — the canonical public operator catalog;
- `POST /api/v1/workflows/validate` — Workflow structural and parameter validation;
- `POST /api/v1/workflows/plan` — deterministic data-free planning;
- `POST /api/v1/workflows/contract` — canonical external-layer preparation requirements;
- `POST /api/v1/workflows/graph` — canonical JSON dependency graph;
- `POST /api/v1/workflows/explain` — canonical review explanation with resolved parameter provenance.

The server delegates those operations directly to public `starshine_geo` APIs. Starshine Workflow
diagnostics, plan-derived requirements, graph structure, parameter defaults, and CRS semantics remain
authoritative in the Core; the HTTP layer only transports their JSON reports.

Install the optional server dependencies in a development checkout:

```bash
python -m pip install -e ".[server]"
python -m uvicorn starshine_server.app:create_app --factory --host 127.0.0.1 --port 8000
```

Interactive OpenAPI documentation is then available at `/api/docs`.

## Intentionally absent in 0.8A

The foundation does **not** accept vector-file uploads, execute workflows, retain projects, create
accounts, fetch URLs, start arbitrary processes, or persist user data. Those capabilities introduce
resource, security, and lifecycle boundaries and must not arrive accidentally as side effects of a
thin API adapter.

## Data-aware assurance before execution

The next platform increment accepts **small inline GeoJSON FeatureCollections for Preflight only**.
This is deliberate: it proves that the service adds Starshine's actual value—early, deterministic
assurance—before introducing execution lifecycle infrastructure.

- `GET /api/v1/limits` publishes the current inline request boundary.
- `POST /api/v1/workflows/preflight` accepts one Workflow plus named inline FeatureCollections and
  returns the canonical `starshine_geo.preflight_workflow_inputs` report.
- invalid data remains a normal Preflight report with `valid: false` when the Core can diagnose it;
- structurally invalid Workflows retain the stable Workflow diagnostic response;
- Server capacity limits return HTTP 413 before spatial execution;
- workflow execution remains explicitly disabled in the assurance-only increment.

Current inline Preflight limits are intentionally small: a 2 MiB request body, at most 8 named
layers, 16 Workflow steps, 2,000 features per layer, and 5,000 features in total. These are service
boundaries, not claims about Core algorithm capacity.

See [PRODUCT.md](PRODUCT.md) for why assurance precedes upload/job infrastructure.

## Bounded synchronous execution

The next increment enables **small inline GeoJSON execution** only after canonical Preflight passes:

- `POST /api/v1/workflows/execute` requires an explicit Workflow-produced output layer;
- the HTTP process never calls `run_workflow()` directly;
- the Server serializes the reviewed request into a private temporary workspace and marks the request
  artifact read-only before execution;
- the only child command is the fixed `python -I -m starshine_server.worker` entrypoint with
  Server-created request/response paths and `shell=False`;
- the child environment drops common credential-bearing variables;
- a cross-platform supervisor enforces 10 seconds wall time and 512 MiB resident memory across the
  worker process tree;
- the serialized HTTP result is capped at 8 MiB;
- timeout or memory failure kills the worker tree;
- failed Preflight returns before a child is started;
- a successful response returns the selected GeoJSON result, the canonical Core manifest, the
  canonical Preflight report, and the static execution policy.

The execution endpoint reuses the same 2 MiB request, 8-layer, 16-step, 2,000-features-per-layer and
5,000-total-features limits as inline Preflight. These values are service policy, not Core capacity.

The temporary workspace is deleted after every request. No client filesystem path, URL, module name,
shell fragment, or plugin identifier is accepted by this execution surface.

This is intentionally synchronous. A queue is not added until measured workloads demonstrate that
the bounded 10-second service is insufficient.

## Canonical review reports for browser clients

Before browser work begins, the Server exposes the Core's existing data-free review reports as JSON.
The three review endpoints all accept the same `WorkflowRequest` shape as validation/planning:
one Workflow plus the names of its external layers.

`contract`, `graph`, and `explain` are not Server-side reimplementations. They call
`build_workflow_contract()`, `build_workflow_graph()`, and `explain_workflow()` directly. Their
`plan_digest` values therefore remain linked to the same canonical plan; the explanation also carries
the canonical graph digest.

No Markdown or Mermaid rendering endpoint is introduced. A future browser can render the returned
structured reports for people without becoming responsible for planning, default resolution,
dependency analysis, operator metadata, or CRS rules. The Core references remain
[WORKFLOW_CONTRACTS.md](WORKFLOW_CONTRACTS.md), [WORKFLOW_GRAPH.md](WORKFLOW_GRAPH.md), and
[WORKFLOW_EXPLAIN.md](WORKFLOW_EXPLAIN.md).

## Reference handoff before Web UI

`examples/server_handoff.py` is the single user-facing reference for the current HTTP product spine.
It deliberately uses only the Python standard library and the public HTTP API; it does not import
`starshine_geo` or `starshine_server`, and it is not a second CLI or SDK.

The example reuses the existing tracked synthetic zone/site workflow and performs the sequence:

`health + limits → validate → plan → Preflight → execute → result + manifest`

Before execution it requires a valid Preflight report. After execution it requires the returned
Preflight report to match the one already reviewed and requires the execution policy to match the
limits discovered before the run. It then writes only a compact evidence set: health, limits,
validation, plan, Preflight, result, manifest, and a deterministic handoff summary.

Focused Server CI starts a real local Uvicorn process and runs this client over HTTP. The existing
`scripts/smoke_installed_server.py` remains the sole owner of exact-wheel Server evidence; the
reference client does not create another release-validation path.

This reference path provides the interaction sequence that the browser workbench simplifies rather
than encouraging the browser to invent parallel GIS semantics.

## Review-first Workbench shell

The first browser surface is packaged inside `starshine_server` and served at `/workbench/` from
the same origin as the API. It has no Node build, CDN, third-party browser runtime, external fonts, or
separate deployment process. The same HTML/CSS/JavaScript assets are required in both the wheel and
source distribution and are exercised by the installed-wheel Server smoke.

The initial slice is data-free: a user can edit Workflow JSON and external layer names, inspect the
canonical operator catalog, validate the Workflow, and review plan/contract/graph/explain reports.
The browser verifies that the reports share the same canonical plan/graph evidence chain, but it does
not derive that chain itself.

Browser rendering uses DOM element creation and `textContent` for report/user text. The source
boundary tests reject dynamic HTML/code sinks and external browser runtimes. The Workbench now has an
explicit bounded execution control, but still has no persistence, file upload, map, or browser GIS
library.

As the Workbench grew from review into drafting and Preflight, presentation was split before adding
more UI. The dependency direction is:

`app.js → render.js facade → render_ui / render_review / render_editor / render_preflight → dom.js`

The facade keeps one stable presentation import for orchestration. Domain render modules receive data
and create DOM only; tests prohibit them from importing transport, draft-transformation, or assurance
modules and from containing API paths or network calls. Shared DOM primitives remain isolated in
`dom.js`. This keeps future CRS/provenance or map presentation from accumulating in one renderer
without introducing a frontend framework or build step.

## Catalog-assisted Workflow drafting

The next Workbench increment adds one draft-step helper without introducing a browser validation
engine. Operator choices, named input roles, parameter descriptions, required/default metadata,
parameter JSON Schema hints, output-CRS behavior, and input contracts all come from the canonical
operator catalog returned by the Server. For each selected input, the existing editor renderer shows
the unresolved geometry types, full CRS contract object, required-field declarations, written-field
declarations, and catalog notes. It does not resolve parameter-driven field names or decide whether a
real layer is compatible.

Non-empty parameter controls accept JSON syntax only; JSON strings therefore need quotes. This is a
syntax boundary, not a second schema validator: the browser does not interpret ranges, enums,
patterns, CRS rules, field requirements, or operator-specific constraints.

The browser does not copy Core defaults into untouched optional parameters. Leaving an optional field
blank omits it from the draft step so `starshine_geo` remains responsible for default resolution.
Required fields may also be left blank; the builder does not pretend that a draft is valid. After a
step is inserted into the editable Workflow JSON, the normal Server review path remains the only
authority that accepts or rejects it.

Input controls suggest declared external layer names and outputs already present in the editable
Workflow. Suggestions are convenience only; dependency validity, duplicate outputs, missing inputs,
parameter rules, CRS validity, and every other Workflow semantic remain Core concerns.

The transformation logic lives in a DOM-free `editor.js` module and is exercised directly in CI
without a frontend package manager. It contains no operator-specific branches or names. The existing
`render_editor.js` remains the single catalog-guidance presentation owner; no parallel authoring or
guidance module is introduced. Rendering consumes catalog metadata generically, while `app.js` only
coordinates the draft and canonical review lifecycle.

Any edit to Workflow JSON or external layer names invalidates the currently displayed review evidence
until the Server review is run again. This prevents stale plan/contract/graph/explain output from being
presented as evidence for a changed Workflow.

## Review-bound inline GeoJSON Preflight

The next Workbench slice reuses the existing bounded inline Preflight endpoint without opening a file
upload boundary. A successful data-free review is required first. Its canonical
`required_external_layers` list becomes the only source of data-slot names, while the already
returned contract provides preparation hints for each slot.

Users paste JSON into those named slots. The browser parses JSON syntax only. It does not check
FeatureCollection structure, geometry type, CRS, required fields, or feature counts. Those checks,
together with request/layer/feature limits, remain in Starshine Server and Core. The current
`GET /api/v1/limits` values are shown as information but are not reimplemented as browser
enforcement.

The browser keeps pasted drafts in memory only. A Workflow or external-layer-name edit invalidates
both the current review and any displayed Preflight evidence. Editing only pasted data invalidates
Preflight while leaving the data-free review current.

Before a Preflight report is displayed as current evidence, its `plan_digest` and
`contract_digest` must match the current canonical review. The UI then renders Core-owned layer
status, feature/CRS/geometry summaries, findings, remaining execution-time checks, and the Preflight
digest.

The DOM-free `assurance.js` module owns only required-layer extraction, JSON parsing, request
construction, and digest-chain comparison. CI deliberately feeds it arbitrary non-GeoJSON JSON to
prove that it is not a client-side GIS validator.

File upload and a map surface remain later decisions. Paste-first Preflight proves the data-aware
assurance flow without simultaneously introducing upload lifecycle, filename/content-type policy,
temporary storage, or browser GIS dependencies. A passing current Preflight is now the mandatory
browser prerequisite for the separately bounded execution flow described below.

## Canonical CRS assumptions and pre-execution evidence

The Workbench now has a dedicated `CRS & Evidence` presentation surface built on the split
presentation boundary. `render_assumptions.js` depends only on shared DOM primitives and receives
canonical report data from `app.js`; it does not fetch, validate, plan, or transform data.

The view presents existing Core-owned information without reinterpretation:

- external-layer CRS contract mode, parameter/value metadata, and equivalence targets from Contract;
- canonical geometry and required-field preparation requirements;
- Explain input provenance, including whether an input is external or produced by an earlier step;
- resolved parameter values together with their canonical `provided/default` source;
- per-step output layer, `output_crs` behavior, deterministic flag, and terminal status;
- Workflow, Operator Catalog, Plan, Contract, Graph, Explanation, and current Preflight digests.

Preflight evidence follows the existing Preflight lifecycle. If pasted inline data changes, the
Preflight digest disappears from this view while the still-current data-free review remains. If the
Workflow or declared external layers change, the complete CRS/evidence view is reset until canonical
Review succeeds again.

This is presentation, not a CRS engine. Browser code does not parse EPSG semantics, prove CRS
equivalence, recommend projections, infer reprojection, or calculate output CRS.

Before execution, this view remains a pre-execution evidence chain. After an explicit bounded run,
the view adds only the workflow and output-result digests already present in the Core-generated
manifest; it does not synthesize a browser provenance model.

## Review-bound browser execution and result provenance

The Workbench can now call the already-existing bounded synchronous execution endpoint, but only
after the current Workflow has successful Review evidence and the current inline layer data has a
passing canonical Preflight. The exact Workflow + layer object envelope retained from that Preflight
is reused for execution rather than reparsing the editor state.

Output choices come only from the current canonical plan's `terminal_layers`. The browser therefore
does not infer which intermediate/result layer should be executed. The Server remains authoritative
and reruns its own canonical Preflight before starting the isolated worker.

The browser checks transport/evidence continuity only:

- execution reports `succeeded` for the output explicitly requested;
- returned Preflight digest/plan/contract evidence matches the current passing Preflight;
- returned execution policy matches the limits discovered from the Server;
- a result object and Core-generated reproducibility manifest are present.

It does **not** validate result geometry, recompute a digest, infer CRS, repair the result, or generate
manifest fields. `execution.js` is DOM-free and contains only generic request/evidence mechanics;
`render_execution.js` is presentation-only behind the existing render facade.

Changing Workflow/layer-name text invalidates Review, Preflight, and result evidence. Changing pasted
inline data invalidates Preflight and result evidence while retaining the still-current data-free
Review. Starting a new Preflight also invalidates any previous execution evidence before the new
report is known.

A map is intentionally deferred. The raw result and canonical manifest are made auditable first so a
later visual layer can consume established result evidence rather than becoming part of execution
semantics.

## Projection-free canonical result preview

A successful current browser execution can now be viewed as a local SVG coordinate-space preview.
This is intentionally **not** a projection-aware map and does not introduce a browser GIS runtime.

`preview.js` receives only the canonical execution result and performs one presentation transform:
finite two-dimensional coordinates are fitted into a fixed SVG viewport while preserving aspect
ratio. Point/MultiPoint, LineString/MultiLineString, Polygon/MultiPolygon, and GeometryCollection
fragments are drawn when their coordinate arrays are usable. Malformed fragments are ignored rather
than converted into browser validation findings.

The preview does not read CRS metadata, look up EPSG definitions, reproject coordinates, calculate
distance/area, test topology, repair geometry, query spatial relationships, load tiles, or contact a
network service. `render_preview.js` only creates SVG/DOM elements.

The raw result and Core-generated manifest in the Execute view remain authoritative. If the SVG is
empty, incomplete, or visually distorted because raw coordinates are not appropriate for direct
screen-space fitting, the canonical execution evidence is unchanged.

The preview shares the execution lifecycle: any edit or new Preflight that invalidates current
execution evidence also clears the preview. This gives the Workbench a bounded visual result surface
without committing Starshine to Leaflet, MapLibre, OpenLayers, a tile provider, or a browser
projection engine.

## Next platform increments

### 0.8C — Web workbench

Build the browser UI from server/core contracts: operator catalog, workflow editor, plan/graph/explain,
Preflight findings, and map preview. Browser code must not duplicate operator validation or CRS
semantics.

### 0.8D / 0.9 — persistence and collaboration

Only after real use requires them, add authenticated projects, object storage, bounded background
jobs, deployment observability, and an optional PostGIS adapter.

The tracked plan and acceptance criteria are maintained in GitHub issue #126.
