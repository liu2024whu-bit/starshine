# Project history and provenance

## Origin

The public Starshine core was extracted in July 2026 from a longer-running private team project focused on spatial data analysis, PostGIS-aware workflow planning, reproducible GIS execution, and web-based result presentation.

The private research repository is `supermap-team/chaotu`. It remains private because it contains unreleased research work, large datasets, internal delivery material, and components that have not completed public licensing and reproducibility review. The public core is maintained as a separate open-source product rather than a temporary mirror.

## Verifiable maintenance record

The primary maintainer is `liu2024whu-bit`, who also has administrator access to the private team repository. Before this public extraction, the private project had already established:

- a branch-and-pull-request workflow with more than fifty numbered pull requests;
- repeated Python test-suite, compilation, frontend-build, and browser-validation records;
- a modular Python analysis core, a versioned FastAPI boundary, Vue and Streamlit clients, and controlled PostGIS workflows;
- explicit credential, runtime-output, CRS, geometry, and operator-boundary policies;
- structured project status, architecture decisions, file indexes, integration logs, and known-issue tracking.

Representative private maintenance references available for verification on request include PRs `#40` through `#59`, covering the Vue client, database sensing, workflow contracts, result maps, report export, portable startup, operator quality, and textbook-informed method validation. The public repository does not claim those private modules as already released here; it records the engineering lineage from which this smaller public contract was selected.

## Public maintenance commitment

Starshine will remain public. The maintainers plan to move components from the private research system only after they pass four gates:

1. redistribution and data-rights review;
2. removal of private credentials, paths, and runtime artifacts;
3. focused tests and documented GIS assumptions;
4. stable public API and contribution documentation.

This provenance statement is factual and intentionally avoids fabricated stars, downloads, users, or public history.
