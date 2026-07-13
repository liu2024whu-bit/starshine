# Changelog

All notable public changes are documented here.

## [Unreleased]

### Added

- deterministic synthetic small-vector cases for buffer, dissolve, point summary, and multi-step
  workflows;
- a machine-readable benchmark report schema with corpus, case, output, environment, and timing
  fields;
- separate semantic verification, report checking, CI execution, and benchmark artifact upload;
- public reproduction guidance that avoids fragile wall-clock pass/fail thresholds;
- clean Python 3.10–3.12 jobs that install the exact CI-built wheel without an editable checkout;
- an installed-wheel smoke script covering package location, public imports, CLI versioning,
  structured validation diagnostics, synthetic workflow execution, and manifest metadata;
- concise installation and smoke logs retained only when a wheel matrix job fails;
- a deterministic `inspect_feature_collection()` API and `starshine inspect` command;
- schema-checked inspection reports containing counts, property fields, declared CRS, bounds, and a
  collection digest without copying feature content.

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
