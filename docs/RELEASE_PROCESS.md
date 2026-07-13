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

## Installed-wheel verification

Source-checkout tests use an editable installation so contributors can iterate quickly. They do not,
by themselves, prove that a built wheel contains every required module, declares every runtime
dependency, or exposes the console entry point correctly.

CI therefore builds the wheel once and passes that exact artifact to clean Python 3.10, 3.11, and
3.12 jobs. Those jobs do not check out the repository and do not use `pip install -e`. They install
the downloaded wheel and run `scripts/smoke_installed_wheel.py`, which verifies:

- the package imports from the installed environment rather than the working tree;
- `starshine --version` matches installed package metadata;
- top-level public callables are available;
- the installed inspection API and `starshine inspect` command produce matching reports;
- valid and invalid workflow diagnostics work through the installed console command;
- a self-created point-within-polygon workflow runs through both the Python API and CLI;
- the generated result and reproducibility manifest contain the expected public values.

Installation and smoke output are retained as short CI artifacts when a matrix job fails. The smoke
script is also required to be present in the source distribution so third parties can repeat the same
check after building locally.

## GitHub release

After the release commit is on `main` and CI is green:

1. create an annotated tag named `vX.Y.Z` at the verified release commit;
2. create a GitHub Release from that tag;
3. use the matching file under `docs/releases/` as the release description;
4. attach the CI-produced `starshine-geo-dist` artifact after checking its digests;
5. keep any external package-index publication as a separate, explicit maintainer decision.

A release must never be created from an unreviewed local directory or from files copied out of a
private repository.
