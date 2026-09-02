# Roadmap

Starshine is developed from the public repository and its synthetic, redistributable evidence. The
roadmap is a guardrail against adding disconnected features faster than the architecture and review
surface can absorb them.

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

## Next — 0.6 engineering consolidation

The next phase is intentionally **not another broad operator expansion**. The priority is to make the
existing public surface easier to understand, verify, and extend.

- [ ] publish a reproducibility note from an independent environment
- [x] enforce documentation-index ownership, local-link validity, and documentation-tree containment
  in the existing public-repository audit
- [ ] audit the documentation set for duplicated or conflicting normative statements now that every
  top-level page is forced through the ownership index
- [x] remove the temporary second console entrypoint and enforce one installed command tree
- [x] retire private CLI input-binding migration shims so Preflight and Run use one planner directly
- [ ] continue the public Python/CLI overlap audit across inspection, inventory, report output, and I/O
  adapters; consolidate only when it removes real branches or repeated policy
- [ ] strengthen dependency-direction checks where remaining public modules still rely only on
  documentation rather than executable architecture tests
- [ ] improve failure diagnostics where two layers currently report the same root cause differently
- [ ] review the current operator set against concrete spatial-analysis gaps before proposing 0.7;
  add an operator only when it reuses the existing registry, contracts, Preflight, tests, and evidence
  model instead of creating a parallel execution path

A feature is not considered complete merely because its implementation works. New public behavior must
have a clear owner in the architecture, a stable contract, synthetic or redistributable evidence,
appropriate tests, documentation without duplication, and clean distribution/reproduction coverage.

For 0.6, deletion, consolidation, executable architecture rules, and clearer diagnostics are preferred
over increasing module count. A 0.7 feature phase should begin only after the remaining overlap and
normative-document audits are small enough that new behavior has an obvious place to live.

See [the documentation index](docs/README.md) for the current ownership map.
