# Project history and provenance

## Origin

The public Starshine core was initially established in July 2026 after a longer-running private
team project had developed experience in spatial data analysis, reproducible GIS execution, and
reviewed workflow boundaries.

The private research repository is `supermap-team/chaotu`. It remains private because it contains
unreleased research work, large datasets, internal delivery material, and components that have not
completed public licensing and reproducibility review. Starshine is maintained as a separate
open-source product rather than a temporary mirror.

## Verifiable maintenance background

The primary maintainer is `liu2024whu-bit`, who also has administrator access to the private team
repository. Before Starshine was created, that project had already established a branch-and-pull-
request workflow with more than fifty numbered pull requests, repeated test and build records, and
explicit credential, output, CRS, geometry, and operator-boundary policies.

Representative private maintenance references may be made available for eligibility verification,
but this repository does not claim private modules as public Starshine functionality. Historical
maintenance evidence explains the maintainer's background; it is not a substitute for Starshine's
own public commits, issues, CI records, releases, or users.

## Independent public development

Since the public repository was established, Starshine changes are designed and implemented from
its own public code and public requirements. Private source files and datasets are not consulted as
implementation material. Shared domain concepts such as CRS validation or bounded operator
registries are re-specified through public contracts, implemented here, and tested with synthetic
fixtures created for Starshine.

Starshine will remain public. New functionality must pass four public gates:

1. an independently written public requirement or issue;
2. redistribution, data-rights, and credential review;
3. synthetic or explicitly redistributable fixtures with focused tests;
4. a stable public API, documentation, CI, and pull-request record.

This provenance statement is factual and intentionally avoids fabricated stars, downloads, users,
or public history.
