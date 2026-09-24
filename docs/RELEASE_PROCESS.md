# Release process

Starshine releases are assembled entirely from the public repository. Private research code, data,
paths, credentials, and unpublished claims are outside the release boundary.

## Version source

`pyproject.toml` is the distribution-version source. Runtime code reads the installed package
metadata through `importlib.metadata`; it does not maintain a second hard-coded version string.

The development branch uses a PEP 440 `.devN` version for the next intended release line. This keeps
CI-built wheels from reusing the version of the latest stable snapshot while work remains under
`[Unreleased]`. `CITATION.cff` and `docs/releases/<version>.md` continue to identify the latest
stable release until a new stable release is intentionally prepared.

Before a release:

1. replace the development `project.version` with the stable `X.Y.Z` version in `pyproject.toml`;
2. move completed entries from `Unreleased` into a dated `CHANGELOG.md` section;
3. update `CITATION.cff` to the same stable version and date;
4. create or update `docs/releases/X.Y.Z.md` and change the README from development-snapshot status
   to the stable release status;
5. confirm the roadmap reflects completed and deferred work;
6. run the public repository audit and all CI jobs.

## Local verification

```bash
python -m pip install --upgrade pip
python -m pip install --constraint requirements/ci-validation.txt -e ".[dev,geopackage,release]"
python scripts/audit_public_repository.py
python scripts/check_release_readiness.py --require-release
python scripts/verify_teaching_examples.py
python -m benchmarks.verify
python -m benchmarks.run --repeat 3 --output benchmark-report.json
python scripts/check_benchmark_report.py benchmark-report.json
python -m benchmarks.spatial_index --repeat 3 --output spatial-index-report.json
python scripts/check_spatial_index_benchmark.py spatial-index-report.json
ruff check .
python -m pytest
python scripts/refresh_public_evidence.py
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

Normal pull-request and `main` CI run the release-readiness checker in development mode: the
distribution version may be a `.devN` snapshot while the citation, dated changelog section, and
versioned release notes continue to identify the latest stable release. The explicit
`--require-release` mode used above rejects development versions and requires package, citation,
README, changelog, and release-note metadata to describe the same stable version before tagging.

The artifact inspector checks that exactly one wheel and one source distribution were produced, that
their filenames and metadata match `pyproject.toml`, that the source distribution includes the
latest stable release notes, and that no unsafe archive paths, ignored caches, private-artifact
directories, or unexpectedly large members were packaged. A development artifact therefore has a
development filename while retaining the last stable release snapshot as historical release evidence.

After artifact inspection, CI also packages the exact wheel with the public installed-core harness,
report checker, schema, hashes, and instructions as `independent-reproduction.zip`. A dedicated
no-checkout smoke job extracts that bundle and executes it in a fresh virtual environment. This
proves the handoff artifact is usable; because the job is still maintained by this repository, its
result is not counted as the independent external reproduction required by issue #105.

## Build and metadata format policy

Release artifacts are part of the reproducibility contract, not an incidental by-product of whatever
build backend happens to be newest on the day a commit is tested. `build-system.requires` therefore
pins the exact reviewed Hatchling release used inside PEP 517's isolated build environment. Updating
that pin is an explicit artifact-format change and requires rebuilding the wheel and sdist, running
Twine validation, archive inspection, and all clean installed-wheel matrices.

The current reviewed pair is Hatchling 1.32.3 with Twine 7.0.0. Hatchling 1.32.3 emits Core Metadata
2.5 by default; Twine 7 validates that metadata through a current `packaging` implementation. Normal
CI fixes Twine to the reviewed version in `requirements/ci-validation.txt`, while the `release` extra
permits compatible Twine 7.x maintenance releases for manual/latest-compatible validation. Runtime
requirements are unaffected by this release-toolchain policy.

Do not resolve a metadata-version mismatch by editing a built wheel, suppressing `twine check`, or
silently downgrading metadata after the build. Change the builder/validator contract explicitly and
re-run the same artifact through the complete release evidence chain.

## CI validation dependency policy

Pull-request and `main` CI resolve the direct validation tools through
`requirements/ci-validation.txt`. The file pins Ruff, pytest, jsonschema, build, and twine to one
reviewed baseline so an unrelated upstream release cannot silently change the evidence produced for
the same Starshine commit. It is a constraints file rather than a complete lockfile: runtime
requirements and transitive packages continue to resolve within the bounds declared by
`pyproject.toml`. The isolated build backend is the exception: because it directly determines the
contents and metadata of the release artifacts, its exact version is fixed in `[build-system]`.

The separate `Latest Compatible Dependencies` workflow runs weekly and on manual dispatch without
the constraints file. It installs the newest `dev` and `release` tool versions permitted by
`pyproject.toml`, runs the supported-Python test matrix, and rebuilds and inspects the distribution.
A failure there is a compatibility signal; it must not be fixed by weakening normal CI or silently
widening package bounds.

Constraint updates require a focused public change. Review the candidate versions, run both the
constrained CI path and the latest-compatible path, record any artifact-format or upper-bound
decision, and change only the direct pins that have been verified. Do not use this file to pin
Starshine's runtime dependencies or to mask an incompatibility that belongs in `pyproject.toml`.

## Installed-wheel verification

Source-checkout tests use an editable installation so contributors can iterate quickly. They do not,
by themselves, prove that a built wheel contains every required module, declares every runtime
dependency, or exposes the console entry point correctly.

CI therefore builds the wheel once and passes that exact artifact to clean Python 3.10 through
3.14 jobs. Those jobs do not check out the repository and do not use `pip install -e`. They install
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
  point-in-polygon joining, pairwise intersection, and polygon-mask Difference work through
  installed APIs and workflow execution;
- the installed inspection API and `starshine inspect` command produce matching reports;
- valid and invalid workflow diagnostics work through the installed console command;
- a self-created point-within-polygon workflow runs through both the Python API and CLI;
- the generated result and reproducibility manifest contain the expected public values.

Installation and smoke output are retained as short CI artifacts when a matrix job fails. Installed
evidence has explicit ownership so adding a public operator does not automatically add another smoke
script:

- `smoke_installed_wheel.py` owns the broad installed package/API/CLI surface;
- `reproduce_installed_core.py` owns the portable end-to-end workflow path and representative
  Intersection/Difference overlay evidence used by the independent-reproduction bundle;
- focused smoke scripts are reserved for behavior the portable core cannot represent naturally,
  such as SARIF failure output, geometry-quality failure/privacy behavior, and optional GeoPackage
  file I/O.

The installed-wheel scripts and the self-created reproduction harness are required in the source
distribution so third parties can repeat the same checks after building locally. The standard wheel
matrix runs the reproduction harness on Python 3.10 through 3.14. A second matrix installs the exact
same wheel on Linux, Windows, and macOS with Python 3.14 and runs the harness without checking out
the repository. Schema validation of the reproduction report is deliberately performed in the
source/dev job; the end-user wheel jobs require only the normal runtime dependencies. The benchmark
artifact contains both the complete corpus report and the indexed-versus-exhaustive report;
semantic equality is mandatory while timing has no shared-runner threshold.

## GitHub release

After the release commit is on `main` and CI is green:

1. create an annotated tag named `vX.Y.Z` at the verified release commit;
2. create a GitHub Release from that tag;
3. use the matching file under `docs/releases/` as the release description;
4. attach the CI-produced `starshine-geo-dist` artifact after checking its digests;
5. keep any external package-index publication as a separate, explicit maintainer decision.

A release must never be created from an unreviewed local directory or from files copied out of a
private repository.
