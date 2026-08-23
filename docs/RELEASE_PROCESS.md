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
python -m pip install --constraint requirements/ci-validation.txt -e ".[dev,geopackage,release]"
python scripts/audit_public_repository.py
python scripts/check_release_readiness.py
python scripts/verify_teaching_examples.py
python -m benchmarks.verify
python -m benchmarks.run --repeat 3 --output benchmark-report.json
python scripts/check_benchmark_report.py benchmark-report.json
python -m benchmarks.spatial_index --repeat 3 --output spatial-index-report.json
python scripts/check_spatial_index_benchmark.py spatial-index-report.json
ruff check .
pytest
python -m build
python -m twine check dist/*
python scripts/check_release_artifacts.py dist
starshine doctor --format json
python scripts/reproduce_installed_core.py --output reproduction-report.json
python scripts/check_reproduction_report.py reproduction-report.json
starshine operators --output operators.json
starshine plan examples/plan.workflow.json --layer-name source --layer-name mask
starshine graph examples/plan.workflow.json --layer-name source --layer-name mask
starshine explain examples/plan.workflow.json --layer-name source --layer-name mask
starshine contract examples/plan.workflow.json --layer-name source --layer-name mask
starshine preflight examples/plan.workflow.json --layer source=examples/data/clip-source.geojson --layer mask=examples/data/clip-mask.geojson
starshine preflight examples/plan.workflow.json --layer source=examples/data/clip-source.geojson --layer mask=examples/data/clip-mask.geojson --format sarif --sarif-root . --output preflight.sarif
starshine preflight examples/plan.workflow.json --layer source=examples/data/clip-source.geojson --gpkg-layer mask study.gpkg analysis_mask
```

The release-readiness check verifies that package metadata, citation metadata, the dated
changelog section, README status and release link, and `docs/releases/<version>.md` all describe the
same current version. The artifact inspector then checks that exactly one wheel and one source
distribution were produced, that their versions match package metadata, that expected public files
are present, and that no unsafe archive paths, ignored caches, private-artifact directories, or
unexpectedly large members were packaged. The source distribution must include the current
versioned release notes, the reviewed CI constraints, the synthetic teaching inputs, their expected
inspection report, focused documentation, and the public verification scripts.

## CI validation dependency policy

Pull-request and `main` CI resolve the direct validation tools through
`requirements/ci-validation.txt`. The file pins Ruff, pytest, jsonschema, build, and twine to one
reviewed baseline so an unrelated upstream release cannot silently change the evidence produced for
the same Starshine commit. It is a constraints file rather than a complete lockfile: runtime
requirements and transitive packages continue to resolve within the bounds declared by
`pyproject.toml`.

The separate `Latest Compatible Dependencies` workflow runs weekly and on manual dispatch without
the constraints file. It installs the newest `dev` and `release` tool versions permitted by
`pyproject.toml`, runs the supported-Python test matrix, and rebuilds and inspects the distribution.
A failure there is a compatibility signal; it must not be fixed by weakening normal CI or silently
widening package bounds.

Constraint updates require a focused public issue and pull request. Review the candidate versions,
run both the constrained CI path and the latest-compatible path, record any upper-bound decision,
and change only the direct pins that have been verified. Do not use this file to pin Starshine's
runtime dependencies or to mask an incompatibility that belongs in `pyproject.toml`.

## Installed-wheel verification

Source-checkout tests use an editable installation so contributors can iterate quickly. They do not,
by themselves, prove that a built wheel contains every required module, declares every runtime
dependency, or exposes the console entry point correctly.

CI therefore builds the wheel once and passes that exact artifact to clean Python 3.10, 3.11, and
3.12 jobs. Those jobs do not check out the repository and do not use `pip install -e`. They install
the downloaded wheel and run the public installed-wheel smoke scripts, which verify:

- the package imports from the installed environment rather than the working tree;
- `starshine --version` matches installed package metadata;
- top-level public callables are available;
- the installed operator catalog includes the reviewed registry and matches the CLI output;
- the installed workflow planner, graph exporter, explanation renderer, and input-contract builder match their CLI forms without loading data;
- the installed input-preflight facade, internal checking/report modules, and CLI agree when
  checking real synthetic GeoJSON layers;
- the installed SARIF adapter and CLI agree on repository-relative locations and empty passing results;
- the installed geometry-quality API, Markdown renderer, and CLI agree on invalid topology, duplicate
  geometry, privacy boundaries, and exit codes;
- separate clean-wheel jobs install the `geopackage` extra and verify explicit multi-layer and mixed
  Preflight bindings, repository-relative SARIF locations, pre-I/O duplicate checks, and source
  overwrite protection on every supported Python version;
- reprojection, projected geometry metrics, deterministic STRtree-backed nearest matching,
  point-in-polygon joining, and pairwise intersection overlay work through installed APIs and
  workflow execution;
- the installed inspection API and `starshine inspect` command produce matching reports;
- valid and invalid workflow diagnostics work through the installed console command;
- a self-created point-within-polygon workflow runs through both the Python API and CLI;
- the generated result and reproducibility manifest contain the expected public values.

Installation and smoke output are retained as short CI artifacts when a matrix job fails. The
installed-wheel scripts and the self-created reproduction harness are required in the source
distribution so third parties can repeat the same checks after building locally. The standard wheel
matrix runs the reproduction harness on Python 3.10, 3.11, and 3.12. A second matrix installs the
exact same wheel on Linux, Windows, and macOS with Python 3.11 and runs the harness without checking
out the repository. The benchmark artifact contains both the complete corpus report and the
indexed-versus-exhaustive report; semantic equality is mandatory while timing has no shared-runner
threshold.

## GitHub release

After the release commit is on `main` and CI is green:

1. create an annotated tag named `vX.Y.Z` at the verified release commit;
2. create a GitHub Release from that tag;
3. use the matching file under `docs/releases/` as the release description;
4. attach the CI-produced `starshine-geo-dist` artifact after checking its digests;
5. keep any external package-index publication as a separate, explicit maintainer decision.

A release must never be created from an unreviewed local directory or from files copied out of a
private repository.
