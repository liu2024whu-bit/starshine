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
- `POST /api/v1/workflows/plan` — deterministic data-free planning.

The server delegates those operations to public `starshine_geo` APIs. Starshine Workflow diagnostics
remain authoritative; the HTTP layer only transports them.

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

The byte limit counts actual received bytes, including chunked requests without `Content-Length`
and requests whose declared length understates their body. The middleware buffers no more than the
limit before invoking the framework; it rejects an oversized stream immediately without draining
its remaining body or calling Core. A client disconnect before the body completes aborts processing.

JSON transport additionally permits at most 64 nested object/array levels (the root is level 1),
published as `max_json_depth`. Non-finite numeric values (including floating-point overflow),
unpaired Unicode surrogates, and decoder representation failures return a bounded HTTP 400
`invalid_json` response without reflecting supplied data. Decoded JSON that exceeds the depth limit
returns HTTP 413; nesting that exhausts the decoder first returns HTTP 400. Ordinary malformed JSON
retains the framework's HTTP 422 syntax diagnostics. This is transport validation only: geometry,
CRS, field contracts and Workflow meaning remain Core responsibilities.

These are per-request boundaries, not a deployment-wide concurrency or slow-client limit. Keep the
unauthenticated development server on loopback; an external deployment still needs explicit access,
connection/time and concurrency controls before being opened to other users.

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
- timeout, memory-limit, monitoring failure, or an unexpected supervision exit triggers bounded
  process-tree termination plus a direct-child kill/wait fallback;
- an unavailable live-process memory reading is an error, never a zero-memory measurement;
- incomplete cleanup returns a service failure rather than reporting a successful execution;
- failed Preflight returns before a child is started;
- a successful response returns the selected GeoJSON result, the canonical Core manifest, the
  canonical Preflight report, and the static execution policy.

The execution endpoint reuses the same 2 MiB request, 8-layer, 16-step, 2,000-features-per-layer and
5,000-total-features limits as inline Preflight. These values are service policy, not Core capacity.

Worker stdout and stderr are discarded. The service returns a stable worker-failure code without
reading, persisting, or echoing unsanitized diagnostics; it does not claim those details are retained.
The temporary workspace is deleted after each completed cleanup. If the operating system denies
termination or a process cannot be reaped within the cleanup timeout, the service reports
`worker_cleanup_failed`; it cannot promise operating-system containment or successful cleanup in
that case. A supervised process tree is not an OS sandbox or a global concurrency control.

No client filesystem path, URL, module name,
shell fragment, or plugin identifier is accepted by this execution surface.

This is intentionally synchronous. A queue is not added until measured workloads demonstrate that
the bounded 10-second service is insufficient.

## Reference handoff before Web UI

`examples/server_handoff.py` is the single user-facing reference for the current HTTP product spine.
It deliberately uses only the Python standard library and the public HTTP API; it does not import
`starshine_geo` or `starshine_server`, and it is not a second CLI or SDK.

The example reuses the existing tracked synthetic zone/site workflow and performs the sequence:

`health + limits → validate → plan → Preflight → execute → result + manifest`

Before execution it requires a valid Preflight report with the same workflow and plan digests as
the reviewed plan. After execution it compares the returned Preflight and execution policy with the
already-reviewed reports, and checks manifest workflow/version/output identifiers. These are
cross-report continuity checks, not a second GIS validator or independent verification of the
server's cryptographic claims. The fixed example writes health, limits, validation, plan, Preflight,
result, manifest and a deterministic handoff summary.

The client reads at most 8 MiB plus one overflow-detection byte per response, rejects unsupported
JSON representations, and closes HTTP error bodies without reading or echoing raw diagnostics.
`--timeout` must be finite and positive; it is a blocking-I/O timeout, not a whole-workflow deadline.
Expected failures produce a concise stderr message and a nonzero exit code rather than a traceback.

Choose a new output directory per attempt. Existing paths are refused before HTTP work and checked
again with exclusive directory creation before writing, so two runs cannot silently overwrite each
other's evidence. `handoff.json` is written last, only after every other file succeeds. A disk/write
failure may leave an incomplete directory without that completion marker; preserve it for inspection
or choose another destination, but do not present it as a successful run. This is not a transactional
database or a durable-storage guarantee.

Focused Server CI starts a real local Uvicorn process and runs the client over HTTP. The existing
`scripts/smoke_installed_server.py` owns the reusable socket/teardown harness, used both by source
tests and by exact-wheel smoke jobs. The smoke artifact includes the same fixed client/workflow/
synthetic inputs, so installed-wheel jobs exercise the client against the installed Server without a
repository checkout. No additional smoke script or generic SDK is introduced.

This reference path is intentionally completed before a browser workbench. It gives Web work a
measured interaction sequence to simplify rather than encouraging the browser to invent parallel GIS
semantics.

## Next platform increments

### 0.8C — Web workbench

Build the browser UI from server/core contracts: operator catalog, workflow editor, plan/graph/explain,
Preflight findings, and map preview. Browser code must not duplicate operator validation or CRS
semantics.

### 0.8D / 0.9 — persistence and collaboration

Only after real use requires them, add authenticated projects, object storage, bounded background
jobs, deployment observability, and an optional PostGIS adapter.

The tracked plan and acceptance criteria are maintained in GitHub issue #126.
