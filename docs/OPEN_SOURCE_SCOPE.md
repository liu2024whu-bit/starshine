# Open-source scope

Starshine is a permanently public, independently maintained geospatial workflow project. Its
historical lineage is documented separately, but current development is based on this repository's
public code, public issues, public reviews, and self-created fixtures.

## Included

- source code designed, reviewed, and maintained in this public repository;
- synthetic GeoJSON, workflow JSON, deterministic benchmark geometries, teaching failure cases,
  and runtime-generated GeoPackage fixtures;
- automated tests, schemas, operator catalogs, reproducibility manifests, benchmark reports, and package-build checks;
- public architecture, security, contribution, release, benchmark, teaching, and roadmap
  documents.

## Excluded

- unreleased research modules or code copied from private repositories;
- private PostgreSQL/PostGIS databases, dumps, credentials, and connection details;
- internal application UI, delivery material, or deployment configuration;
- large experimental rasters and course-delivery artifacts;
- textbook PDFs, OCR output, and materials without explicit redistribution permission;
- historical local logs, personal paths, generated runtime output, and binary research archives.

## Enforcement

`scripts/audit_public_repository.py` runs in CI. It rejects tracked secret patterns, private-origin
references outside the provenance document, personal absolute paths outside synthetic tests,
research-oriented binary formats, ignored cache directories, and unexpectedly large files.
Release archives receive an additional member-level inspection before they can be attached to a
release.

New Starshine functionality is specified from public requirements and implemented against the
public contracts in this repository. A concept that also exists elsewhere must still receive a new
public design, synthetic fixtures, focused tests, and normal pull-request review here; private code
or data is not an implementation dependency.
