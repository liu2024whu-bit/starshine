# Security policy

## Supported versions

Security fixes currently target the latest `0.x` release and the `main` branch.

## Reporting a vulnerability

Do not publish credentials, private data, or a working exploit in a public issue. Contact the primary maintainer through the email listed on the maintainer's GitHub profile and include:

- affected version or commit;
- entry point and required privileges;
- reproducible input with synthetic data;
- expected impact;
- suggested mitigation, if known.

## Security boundaries

Starshine treats workflow files and GeoJSON as untrusted input. The workflow engine uses an explicit registry and never evaluates arbitrary Python. Distance operations require a projected working CRS. Output layers cannot overwrite existing context layers. Repository policy prohibits committed credentials, database dumps, and private datasets.
