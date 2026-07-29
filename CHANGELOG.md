# Changelog

All notable public changes are documented here.

## [Unreleased]

### Added

- a read-only `assess_geometry_quality()` API and `starshine quality` command with schema-checked JSON
  and Markdown reports for invalid topology, empty and duplicate geometry, coordinate dimensions,
  coordinate-count statistics, CRS metadata status, bounded unique finding samples, canonical digest
  availability, fixed-byte-order normalized duplicate keys, and privacy-preserving report digests;
- a synthetic mixed-quality GeoJSON example, tracked reports, focused documentation, architecture and
  package-surface tests, release-archive requirements, and clean installed-wheel coverage.

### Changed

- Workflow Preflight internals are split into a compact public facade, immutable report model,
  finding aggregation, per-layer checks, report assembly, and Markdown rendering modules, with
  architecture tests preventing circular or reversed dependencies while preserving public output.

## [0.4.0] - 2026-07-29

### Added

- a CRS-safe `clip_features()` API and bounded `clip` workflow operation with explicit polygon-mask,
  equivalent-CRS, property-preservation, feature-order, boundary-contact, and empty-result rules;
- synthetic clip examples, Workflow Schema fixtures, installed-wheel coverage, and a fifth public
  benchmark case;
- benchmark corpus versions 2 through 5, expanding the deterministic public suite to eight cases for
  clip, nearest-feature matching, point-in-polygon attribution, and projected geometry metrics;
- a deterministic `plan_workflow()` API and `starshine plan` command with schema-checked dependency,
  layer-provenance, terminal-output, resolved-default, parameter-source, and digest reporting;
- registry-level sensitive-parameter annotations so plans redact marked values before serialization
  and hashing;
- a CRS-safe `nearest_features()` API and bounded `nearest` workflow operation with deterministic
  tie-breaking, optional distance limits, explicit no-match fields, and projected-CRS safeguards;
- a deterministic `join_points_to_polygons()` API and bounded point-in-polygon workflow operation
  with boundary-inclusive matching, explicit ambiguity policy, and retained unmatched points;
- a focused `calculate_geometry_metrics()` API and `geometry_metrics` workflow operation with
  projected-CRS requirements and collision-safe area and length output fields;
- deterministic `build_workflow_graph()` and `render_workflow_mermaid()` APIs plus `starshine graph`,
  with schema-checked JSON graphs and safely escaped Mermaid output derived from canonical plans;
- deterministic `explain_workflow()` and Markdown rendering plus `starshine explain`, with
  plan-derived parameter provenance, graph-linked evidence, and explicit execution-time limitations;
- deterministic `build_workflow_contract()` and `starshine contract`, deriving external-layer
  geometry, CRS, required-field, and field-write preparation rules from planner and registry metadata;
- deterministic `preflight_workflow_inputs()` and `starshine preflight`, checking actual external
  GeoJSON layers for structure, geometry types, CRS rules, required fields, uniqueness, nullability,
  finite scalar values, and output-field collisions without executing operators;
- deterministic `build_workflow_preflight_sarif()` and `starshine preflight --format sarif`,
  converting completed findings to SARIF 2.1.0 with repository-relative locations, logical workflow
  context, stable rules and fingerprints, strict path boundaries, and clean installed-wheel coverage.

### Changed

- pull-request and `main` CI now use reviewed direct-tool constraints for Ruff, pytest, jsonschema,
  build, and twine, while a separate weekly/manual workflow checks the latest versions permitted by
  the project dependency bounds;
- installed-wheel verification now exercises planning, graph, explanation, contracts, preflight,
  SARIF, clipping, nearest matching, spatial joins, projected metrics, inspection, execution, and
  manifests through public APIs and CLI commands on Python 3.10, 3.11, and 3.12;
- release archives now require the complete 0.4 public documentation, schemas, synthetic examples,
  CI constraints, and both installed-wheel smoke scripts.

## [0.3.0] - 2026-07-14

### Added

- deterministic synthetic small-vector cases for buffer, dissolve, point summary, and multi-step
  workflows;
- a machine-readable benchmark report schema with corpus, case, output, environment, and timing
  fields;
- clean Python 3.10–3.12 jobs that install and exercise the exact CI-built wheel without an editable
  checkout;
- a deterministic `inspect_feature_collection()` API and `starshine inspect` command with
  schema-checked structural reports;
- compact synthetic teaching cases for CRS and geometry failure modes with an executable verifier;
- a declarative runtime operator registry and schema-checked `starshine operators` catalog;
- a `reproject_features()` API and `reproject` workflow operation with explicit source/target CRS
  validation;
- a release-readiness check that keeps package, citation, changelog, README, and versioned release
  notes synchronized.

### Changed

- Workflow execution, named inputs, parameter validation, defaults, public schemas, and output-CRS
  behavior now derive from one reviewed operator specification;
- release archive inspection now requires the release-notes file for the current package version
  instead of a hard-coded historical version;
- public examples, benchmarks, teaching fixtures, and installed-wheel checks remain based only on
  synthetic data created in this repository.

## [0.2.0] - 2026-07-13

### Added

- machine-readable JSON Schema for workflow version 1;
- structured workflow diagnostics with stable codes, paths, step indexes, and operation names;
- complete structural and operator-parameter preflight validation before execution;
- operator-specific schemas for buffer, dissolve, and point-within-polygon summary workflows;
- public valid and invalid workflow fixtures checked by an external JSON Schema validator;
- standalone `starshine validate` command with stable JSON diagnostic output;
- opt-in reproducibility manifests with deterministic workflow, input, and output digests;
- CRS reporting and redaction of credentials, absolute paths, and path-like parameters;
- optional GeoPackage adapter with explicit layer selection, CRS preservation, and overwrite guards;
- isolated `geopackage` dependency extra and real round-trip CI with self-created fixtures;
- public repository boundary auditing and release-archive inspection;
- reproducible wheel and source-distribution builds uploaded as CI artifacts;
- documented public release process and versioned release notes.

### Changed

- runtime and manifest versions now come from installed package metadata;
- `dissolve_features` is included in the documented top-level public API;
- README, roadmap, provenance, and open-source-scope language now distinguish historical lineage
  from independent current development.

## [0.1.0] - 2026-07-13

### Added

- independent public package and command-line entry point;
- GeoJSON validation and explicit CRS safeguards;
- buffer, dissolve, and point-within-polygon summary operators;
- versioned bounded workflow engine;
- synthetic example data and reproducible demo;
- tests, CI, Apache-2.0 license, security policy, contribution rules, roadmap, and provenance
  documentation.
