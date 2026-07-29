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

## 0.3 — Declarative registry and external reproduction

- [x] deterministic small-vector benchmark fixtures and machine-readable reports
- [x] installation smoke tests from built wheels on all supported Python versions
- [x] deterministic GeoJSON inspection reports and installed-wheel CLI coverage
- [x] synthetic teaching examples for CRS and geometry failure modes
- [x] declarative operator registry with a machine-readable, schema-checked catalog
- [x] explicit reprojection API and bounded workflow operation

## 0.4 — Bounded analysis and workflow assurance

- [x] CRS-safe clip API and bounded workflow operation with synthetic benchmark coverage
- [x] deterministic data-free workflow planning with dependencies and resolved defaults
- [x] deterministic JSON and Mermaid workflow graph export derived from planning
- [x] data-free Workflow Explain reports and Markdown review narratives
- [x] planner-derived external-layer geometry, CRS, and field contracts
- [x] actual external-layer preflight checks without spatial execution
- [x] deterministic SARIF 2.1.0 export with repository-relative input locations
- [x] CRS-safe nearest-feature matching with deterministic ties and synthetic benchmark coverage
- [x] deterministic point-in-polygon spatial join with explicit ambiguity handling
- [x] projected area and length metrics with explicit CRS and field-collision rules
- [x] reviewed CI validation-tool constraints and scheduled latest-compatible checks

## 0.5 — Maintainable input and performance boundaries

- [ ] allow `starshine preflight` to read explicitly selected GeoPackage layers through the existing
  adapter while keeping the core API FeatureCollection-only
- [x] split Preflight finding aggregation, checks, report assembly, and rendering into one-way
  internal modules before adding a new independent check family
- [ ] add a read-only Geometry Quality Report without automatic repair
- [ ] evaluate STRtree acceleration for nearest matching and point-in-polygon joins against the
  existing deterministic semantics and benchmark corpus
- [ ] publish third-party reproduction notes from an environment not used by the maintainer
- [ ] specify any read-only database adapter through public interfaces and synthetic fixtures

The public repository will remain intentionally focused. Features enter Starshine only after an
independent public specification, licensing and data review, synthetic or redistributable fixtures,
security checks, architecture review, and normal pull-request validation.
