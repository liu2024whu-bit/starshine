# Starshine documentation

This directory is organized by **question**, not by commit or implementation file. Each document should
have one clear owner. If a new feature can be explained by extending an existing document, extend it
instead of creating another page.

## Start here

| Need | Document | Scope |
| --- | --- | --- |
| Understand the codebase | [ARCHITECTURE.md](ARCHITECTURE.md) | Module boundaries, dependency direction, invariants |
| Install and verify a clean environment | [REPRODUCING.md](REPRODUCING.md) | End-to-end installation and reproduction |
| Understand reproducibility evidence | [REPRODUCIBILITY.md](REPRODUCIBILITY.md) | Run manifests and provenance boundaries |
| Understand the public operator surface | [OPERATORS.md](OPERATORS.md) | Registry, catalog, extension contract |
| Understand workflow validation | [WORKFLOW_VALIDATION.md](WORKFLOW_VALIDATION.md) | Workflow structure and diagnostics |
| Understand planning and execution preparation | [WORKFLOW_PLANNING.md](WORKFLOW_PLANNING.md), [WORKFLOW_CONTRACTS.md](WORKFLOW_CONTRACTS.md) | Data-free planning and external-layer contracts |
| Validate real inputs | [WORKFLOW_PREFLIGHT.md](WORKFLOW_PREFLIGHT.md) | Actual input checks before execution |
| Work with GeoPackage | [GEOPACKAGE.md](GEOPACKAGE.md) | Optional adapter, explicit layers and I/O rules |
| Discover an unfamiliar source | [INSPECTION.md](INSPECTION.md) | Deep GeoJSON inspection and privacy-aware inventory |
| Diagnose geometry quality | [GEOMETRY_QUALITY.md](GEOMETRY_QUALITY.md), [VECTOR_QUALITY_GATE.md](VECTOR_QUALITY_GATE.md) | Findings and review gate |
| Understand spatial indexing | [SPATIAL_INDEXING.md](SPATIAL_INDEXING.md) | STRtree design and correctness boundary |
| Compare performance evidence | [BENCHMARKS.md](BENCHMARKS.md) | Synthetic corpus and benchmark interpretation |
| Learn from intentional failures | [TEACHING_FAILURES.md](TEACHING_FAILURES.md) | Synthetic CRS and geometry failure cases |
| Release the package | [RELEASE_PROCESS.md](RELEASE_PROCESS.md) | Build, archive, wheel and release evidence |
| Understand project scope | [OPEN_SOURCE_SCOPE.md](OPEN_SOURCE_SCOPE.md) | Public-data and provenance boundary |

## Operator references

The operator-specific pages are deliberately short and normative:

- [CLIP.md](CLIP.md) — CRS-safe clipping semantics.
- [INTERSECTION.md](INTERSECTION.md) — deterministic pairwise intersection semantics.
- [NEAREST.md](NEAREST.md) — deterministic nearest-feature matching.
- [SPATIAL_JOIN.md](SPATIAL_JOIN.md) — point-in-polygon join and ambiguity rules.
- [GEOMETRY_METRICS.md](GEOMETRY_METRICS.md) — projected length and area requirements.

The common operator registry, naming, schemas and extension rules remain in [OPERATORS.md](OPERATORS.md);
operator pages should not repeat registry-wide rules.

## Workflow references

The workflow documents form one progression:

`validation → planning → contract → preflight → execution → graph/explain → evidence`

- [WORKFLOW_VALIDATION.md](WORKFLOW_VALIDATION.md) defines what a workflow is allowed to contain.
- [WORKFLOW_PLANNING.md](WORKFLOW_PLANNING.md) describes data-free dependency and parameter resolution.
- [WORKFLOW_CONTRACTS.md](WORKFLOW_CONTRACTS.md) turns planning results into external-layer requirements.
- [WORKFLOW_PREFLIGHT.md](WORKFLOW_PREFLIGHT.md) checks real inputs against those requirements.
- [WORKFLOW_GRAPH.md](WORKFLOW_GRAPH.md) and [WORKFLOW_EXPLAIN.md](WORKFLOW_EXPLAIN.md) present the same
  canonical plan for review rather than introducing alternate workflow models.
- [WORKFLOW_PREFLIGHT_SARIF.md](WORKFLOW_PREFLIGHT_SARIF.md) documents the SARIF representation of
  completed Preflight findings.

## Maintenance references

- [ARCHITECTURE.md](ARCHITECTURE.md) is the authority for dependency boundaries.
- [BENCHMARKS.md](BENCHMARKS.md) is the authority for performance-evidence interpretation.
- [RELEASE_PROCESS.md](RELEASE_PROCESS.md) is the authority for distribution verification.
- [PROJECT_HISTORY.md](PROJECT_HISTORY.md) records historical context; it is not a feature specification.
- [VALIDATION.md](VALIDATION.md) contains the compact validation reference used by maintainers.

Release-specific notes live under [`releases/`](releases/) and are snapshots, not additional copies of
current feature documentation.

## Documentation rules

1. **One question, one owner.** Do not create a second page for the same concept.
2. **Reference, don't duplicate.** Link to the authoritative page when a concept crosses boundaries.
3. **Normative vs historical.** Current behavior belongs in the relevant contract or architecture page;
   history belongs in `PROJECT_HISTORY.md` and release notes.
4. **Examples stay close to the contract.** Tracked examples demonstrate behavior; they do not become
   another documentation layer.
5. **Schema files are machine contracts.** Human explanations should link to them rather than copying
   their entire structure into Markdown.
6. **New code does not automatically require new documentation.** First check whether an existing page
   can absorb the feature without becoming ambiguous.

The public-repository audit enforces the structural part of these rules: every top-level Markdown page
under `docs/` must be referenced by this index, local index links must resolve inside `docs/`, and links
that escape the documentation tree are rejected. This does not try to judge prose similarity; it makes
new documentation visible to reviewers so semantic duplication can be caught before merge.

The root `README.md` remains the public landing page and quick-start surface. This index is the map for
contributors and reviewers who need the complete documentation set.
