# Changelog

All notable public changes are documented here.

## [Unreleased]

### Added

- a CRS-safe `clip_features()` API and bounded `clip` workflow operation with explicit polygon-mask,
  equivalent-CRS, property-preservation, feature-order, boundary-contact, and empty-result rules;
- synthetic clip examples, Workflow Schema fixtures, installed-wheel coverage, and a fifth public
  benchmark case;
- benchmark corpus version 2, which identifies reports containing the new clip case;
- a deterministic `plan_workflow()` API and `starshine plan` command with schema-checked dependency,
  layer-provenance, terminal-output, resolved-default, and digest reporting;
- registry-level sensitive-parameter annotations so future plan reports can redact values before
  serialization and hashing;
- a CRS-safe `nearest_features()` API and bounded `nearest` workflow operation with deterministic
  tie-breaking, optional distance limits, explicit no-match fields, planner/catalog integration,
  synthetic examples, installed-wheel coverage, and a sixth public benchmark case;
- benchmark corpus version 3, identifying reports that include nearest-feature matching;
- a deterministic `join_points_to_polygons()` API and bounded point-in-polygon workflow operation
  with boundary-inclusive matching, explicit ambiguity policy, retained unmatched points, planner
  integration, synthetic examples, installed-wheel coverage, and a seventh public benchmark case;
- benchmark corpus version 4, identifying reports that include point-in-polygon attribution;
- a focused `calculate_geometry_metrics()` API and `geometry_metrics` workflow operation with
  projected-CRS requirements, collision-safe output fields, synthetic examples, planner/catalog
  integration, installed-wheel coverage, and an eighth public benchmark case;
- benchmark corpus version 5, identifying reports that include projected geometry metrics;
- deterministic `build_workflow_graph()` and `render_workflow_mermaid()` APIs plus `starshine graph`,
  with schema-checked JSON graphs, safely escaped Mermaid output, plan-derived dependencies, and
  clean installed-wheel coverage;
- deterministic `explain_workflow()` and Markdown rendering plus `starshine explain`, with
  plan-derived parameter provenance, graph-linked evidence, execution-time limitations, a
  machine-readable Schema, and clean installed-wheel coverage.
- deterministic `build_workflow_contract()` and `starshine contract`, deriving external-layer
  geometry, CRS, required-field, and field-write preparation rules from the canonical planner and
  declarative operator input metadata.

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
