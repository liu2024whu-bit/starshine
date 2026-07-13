# Roadmap

Starshine roadmap items are specified and implemented from the public repository. Historical
provenance does not make private source code or data part of the implementation backlog.

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

## 0.2.x — Maintenance and external reproduction

- [ ] small vector benchmark fixtures with machine-readable result summaries
- [ ] installation smoke tests from built wheels on all supported Python versions
- [ ] third-party reproduction notes from an environment not used by the maintainer
- [ ] additional examples for teaching CRS and geometry failure modes

## 0.3 — Community research preview

- [ ] additional overlay and proximity operators designed through public issues
- [ ] optional read-only database adapter specified from public interfaces and synthetic fixtures
- [ ] plugin boundary for independently validated operators
- [ ] documentation examples for education and research replication

The public repository will remain intentionally focused. Features enter Starshine only after an
independent public specification, licensing and data review, synthetic or redistributable fixtures,
security checks, and normal pull-request validation.
