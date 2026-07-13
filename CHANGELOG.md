# Changelog

All notable public changes are documented here.

## [Unreleased]

### Added

- machine-readable JSON Schema for workflow version 1;
- structured workflow diagnostics with stable codes, paths, step indexes, and operation names;
- complete structural and operator-parameter preflight validation before execution;
- operator-specific schemas for buffer, dissolve, and point-within-polygon summary workflows;
- public valid and invalid workflow fixtures checked by an external JSON Schema validator;
- standalone `starshine validate` command with stable JSON diagnostic output;
- opt-in reproducibility manifests with deterministic workflow, input, and output digests;
- CRS reporting and redaction of credentials, absolute paths, and path-like parameters;
- optional GeoPackage adapter contract with explicit layer selection, CRS preservation, and
  overwrite guards;
- isolated `geopackage` dependency extra so base GeoJSON workflows remain lightweight;
- dedicated optional-dependency CI with self-created GeoPackage round-trip and overwrite tests.

## [0.1.0] - 2026-07-13

### Added

- independent public package and command-line entry point;
- GeoJSON validation and explicit CRS safeguards;
- buffer, dissolve, and point-within-polygon summary operators;
- versioned bounded workflow engine;
- synthetic example data and reproducible demo;
- tests, CI, Apache-2.0 license, security policy, contribution rules, roadmap, and provenance documentation.
