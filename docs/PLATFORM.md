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

## Next platform increments

### 0.8B — bounded execution

Add an explicit per-job workspace and hard resource limits before accepting data. Start with GeoJSON,
then add explicitly selected GeoPackage layers. Every execution path must run the existing Preflight
and Workflow engine, preserve immutable inputs, and return result + manifest evidence.

### 0.8C — Web workbench

Build the browser UI from server/core contracts: operator catalog, workflow editor, plan/graph/explain,
Preflight findings, and map preview. Browser code must not duplicate operator validation or CRS
semantics.

### 0.8D / 0.9 — persistence and collaboration

Only after real use requires them, add authenticated projects, object storage, bounded background
jobs, deployment observability, and an optional PostGIS adapter.

The tracked plan and acceptance criteria are maintained in GitHub issue #126.
