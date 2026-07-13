# Release process

Starshine releases are assembled entirely from the public repository. Private research code, data,
paths, credentials, and unpublished claims are outside the release boundary.

## Version source

`pyproject.toml` is the single release-version source. Runtime code reads the installed package
metadata through `importlib.metadata`; it does not maintain a second hard-coded version string.

Before a release:

1. update `project.version` in `pyproject.toml`;
2. move completed entries from `Unreleased` into a dated `CHANGELOG.md` section;
3. update `CITATION.cff` and the release notes;
4. confirm the roadmap reflects completed and deferred work;
5. run the public repository audit and all CI jobs.

## Local verification

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev,geopackage,release]"
python scripts/audit_public_repository.py
ruff check .
pytest
python -m build
python -m twine check dist/*
python scripts/check_release_artifacts.py dist
```

The artifact inspector checks that exactly one wheel and one source distribution were produced,
that their versions match package metadata, that expected public files are present, and that no
unsafe archive paths, ignored caches, private-artifact directories, or unexpectedly large members
were packaged.

## GitHub release

After the release commit is on `main` and CI is green:

1. create an annotated tag named `vX.Y.Z` at the verified release commit;
2. create a GitHub Release from that tag;
3. use the matching file under `docs/releases/` as the release description;
4. attach the CI-produced `starshine-geo-dist` artifact after checking its digests;
5. keep any external package-index publication as a separate, explicit maintainer decision.

A release must never be created from an unreviewed local directory or from files copied out of a
private repository.
