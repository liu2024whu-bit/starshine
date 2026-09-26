# Roadmap

Starshine is developed from the public repository and its synthetic, redistributable evidence. The
roadmap is a guardrail against adding disconnected features faster than the architecture and review
surface can absorb them.

Roadmap headings describe development phases, not proof that every matching package version was
published. The current `main` branch builds `0.7.0.dev0`; the latest stable release metadata remains
`0.4.0` until a separately verified stable release is prepared.

## 0.1 — Public core

- [x] GeoJSON validation
- [x] CRS-aware buffering
- [x] dissolve and point-within-polygon summary
- [x] bounded JSON workflow execution
- [x] command-line demo and synthetic data
- [x] automated tests and CI

## 0.2 — Reproducibility and interoperability

- [x] GeoPackage input/output adapter with optional dependencies
- [x] stable operator-specific JSON Schema for workflow files
- [x] structured diagnostics with step and parameter paths
- [x] result provenance manifest with sensitive-value redaction
- [x] standalone public workflow validation command
- [x] public-boundary audit and reproducible release-artifact checks

## 0.3 — Declarative registry and external reproduction

- [x] deterministic small-vector benchmark fixtures and machine-readable reports
- [x] built-wheel smoke tests across the supported Python matrix
- [x] deterministic GeoJSON inspection reports
- [x] synthetic teaching examples for CRS and geometry failure modes
- [x] declarative operator registry and schema-checked catalog
- [x] explicit reprojection API and bounded workflow operation

## 0.4 — Bounded analysis and workflow assurance

- [x] CRS-safe clip API and workflow operation
- [x] deterministic data-free workflow planning
- [x] workflow graph and Explain reports derived from the canonical plan
- [x] planner-derived external-layer contracts
- [x] actual external-layer Preflight checks
- [x] deterministic SARIF 2.1.0 export
- [x] CRS-safe nearest matching and deterministic point-in-polygon join
- [x] projected area and length metrics with explicit collision rules
- [x] reviewed CI validation constraints and compatibility checks

## 0.5 — Maintainable input and performance boundaries

- [x] explicit GeoPackage layer selection in Preflight
- [x] one-way Preflight internal modules
- [x] read-only Geometry Quality reports and quality gate
- [x] deterministic STRtree acceleration with independent differential evidence
- [x] deterministic pairwise intersection overlay
- [x] path-free runtime doctor and self-created installed-core reproduction
- [x] clean-wheel reproduction on Linux, Windows, and macOS
- [x] direct GeoPackage workflow input/output with collision guards
- [x] privacy-aware GeoJSON/GeoPackage source inventory
- [x] documentation ownership/index to prevent parallel or duplicated documentation

## 0.6 — Engineering consolidation

This phase consolidated the existing public surface instead of expanding it sideways. The internal
architecture, documentation ownership, diagnostics, CLI boundaries, and release evidence work listed
below is complete. One evidence task remains intentionally external: an independent operator or CI
environment must reproduce the clean-wheel handoff before the corresponding note can be published.

- [ ] publish a dated independent-environment reproducibility note after issue #105 has accepted
  external clean-wheel evidence
- [x] enforce documentation-index ownership, local-link validity, and documentation-tree containment
  in the existing public-repository audit
- [x] audit the documentation set for duplicated or conflicting normative statements now that every
  top-level page is forced through the ownership index
- [x] remove the temporary second console entrypoint and enforce one installed command tree
- [x] retire private CLI input-binding migration shims so Preflight and Run use one planner directly
- [x] complete the public Python/CLI overlap audit across inspection, inventory, report output, and I/O
  adapters; consolidate repeated policy while retaining intentional boundary validation
- [x] strengthen dependency-direction checks for data-free planning/report layers with executable
  architecture tests in addition to the existing Preflight, quality, indexing, and CLI/I/O checks
- [x] align duplicate-identifier failures across Preflight and direct operators without echoing
  property values into runtime diagnostics
- [x] review the operator set against concrete spatial-analysis gaps and select polygon-mask
  Difference as the first bounded 0.7 addition because it reuses registry, contracts, Preflight,
  Workflow execution, I/O adapters, tests, and release evidence without a parallel execution path

A feature is not considered complete merely because its implementation works. New public behavior
must have a clear owner on the product spine, a stable contract, synthetic or redistributable
evidence, appropriate tests, documentation without duplication, and clean
distribution/reproduction coverage.

## 0.7 — Stabilize the bounded analysis core

The current 0.7 development line is a stabilization phase, not a mandate to add more overlay
operations. The priority is to prove that the bounded analysis core is understandable, installable,
reproducible, and releasable before expanding the operator catalog again.

- [x] add CRS-safe polygon-mask Difference/Erase through the existing public API and Workflow registry
- [x] provide a portable, checksum-verified independent-reproduction handoff built from the exact
  reviewed wheel
- [x] consolidate installed evidence around explicit owners instead of adding a smoke script for each
  operator or file-format path
- [x] derive wheel and source-distribution package coverage from the actual `src/starshine_geo`
  source tree and verify the supported Python 3.10–3.14 matrix
- [ ] obtain accepted independent clean-wheel evidence for issue #105 and record the dated result
  without treating repository-owned CI as external validation
- [ ] prepare a stable 0.7.0 release candidate only after the independent evidence prerequisite is
  satisfied and the release-readiness chain passes from a stable version commit
- [ ] evaluate another spatial-analysis gap only after real downstream use or a concrete public issue
  demonstrates the need; do not add generic union, identity, or broad join-policy surfaces merely to
  match a larger GIS library

Until those evidence and release conditions are met, maintenance should prefer deleting duplicate
paths, fixing correctness gaps, and simplifying ownership over increasing module or operator count.


## 0.8 — Expose the core through a bounded platform adapter

0.8 begins only after the stable 0.7.0 release is completed. The goal is not to move GIS logic into
HTTP handlers; it is to make the existing auditable core usable from a service and, later, a browser.

### 0.8A — read-only API foundation

- [x] define the one-way `starshine_server → public starshine_geo API` dependency boundary
- [x] add optional FastAPI/Pydantic/Uvicorn server dependencies without changing core-only installs
- [x] expose health/version, canonical operator catalog, Workflow validation, and deterministic plan
- [x] preserve Core Workflow diagnostics at the HTTP boundary
- [x] enforce Core/Server dependency direction with architecture tests
- [x] verify the server from source and from the exact built wheel
- [ ] merge the foundation only after 0.7.0 has been tagged and its release evidence accepted

### 0.8B — data-aware assurance, then bounded execution

- [x] codify the product goal: assurance and reproducibility rather than operator or infrastructure count
- [x] expose bounded inline GeoJSON Preflight through the canonical Core report
- [x] publish request/layer/step/feature limits before enabling execution
- [x] define output-size, wall-clock, and resident-memory execution limits
- [x] add isolated per-request workspaces with read-only serialized execution inputs
- [x] accept bounded inline GeoJSON execution through a fixed supervised child process
- [x] require the existing Preflight path before every execution
- [x] return selected result + manifest evidence without exposing server filesystem paths
- [x] provide one standard-library HTTP handoff with real-Uvicorn CI evidence before designing Web UI
- [ ] add explicit GeoPackage execution input only after a file-upload/container boundary is designed
- [ ] add a job abstraction only when measured runtime requires asynchronous execution

### 0.8C — Web workbench

- [x] expose canonical contract/graph/explain JSON reports before browser code owns any review semantics
- [x] package a same-origin review-only Workbench and verify its assets from the exact Server wheel
- [x] build operator selection and Workflow drafting from the canonical catalog/contracts without client-side validation
- [ ] surface plan/graph/explain and Preflight findings before execution
- [ ] add map preview without reproducing spatial-analysis semantics in JavaScript
- [ ] make CRS assumptions and output provenance visible in the user flow

### 0.8D / 0.9 — persistence and collaboration

Authentication, persistent projects, object storage, PostGIS, and background workers are deferred
until concrete usage demonstrates their need. See issue #126 and [PLATFORM.md](docs/PLATFORM.md).


See [the documentation index](docs/README.md) for the current ownership map.
