# Security policy

## Supported versions

Security fixes target the latest stable release line documented by `CITATION.cff` and
`docs/releases/`, together with the `main` development branch. Older snapshots may receive
documentation-only corrections, but security findings should be reproduced against the latest
public commit when possible.

## Reporting a vulnerability

Do not publish credentials, private data, or a working exploit in a public issue. Contact the
primary maintainer through the email listed on the maintainer's GitHub profile and include:

- affected version or commit;
- entry point and required privileges;
- reproducible input using synthetic or redistributable data;
- expected impact;
- suggested mitigation, if known.

Do not include private database dumps, internal repository files, personal absolute paths, or real
API keys in the report. A minimal synthetic reproducer is preferred.

## Security boundaries

Starshine treats workflow JSON, GeoJSON, and optional GeoPackage inputs as untrusted. The workflow
engine uses an explicit registry and never evaluates arbitrary Python. Distance operations require
a projected working CRS. Output layers cannot overwrite existing context layers, and GeoPackage
writes require explicit overwrite permission.

Repository policy prohibits committed credentials, private datasets, research-delivery artifacts,
and unreleased private source modules. CI audits tracked files for high-confidence secrets,
personal paths, disallowed binary research formats, large files, and private-origin references
outside the provenance document. Built release archives receive a second member-level inspection.
