# Reproducing Starshine from a clean environment

This guide is the shortest supported route from a fresh clone or built wheel to a verified working
Starshine installation. It uses only public repository content and self-created temporary data.

Starshine currently runs its full source and installed-wheel CI on Python 3.10, 3.11, and 3.12.
A separate installed-wheel reproduction matrix also runs on Linux, Windows, and macOS with Python
3.11. The package metadata allows Python 3.10 and newer, but those are the versions and platforms
with explicit public CI evidence.

## 1. Clone and create an isolated environment

```bash
git clone https://github.com/liu2024whu-bit/starshine.git
cd starshine
python -m venv .venv
```

You do not need to activate the environment. On macOS or Linux:

```bash
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/starshine doctor
```

On Windows PowerShell or Command Prompt:

```text
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\starshine.exe doctor
```

A healthy core reports `Starshine doctor: PASS`. The doctor does not read project data or modify
user files. It checks installed package metadata, the PROJ CRS database and a known transform, GEOS
constructive and boundary predicates, the declarative operator registry, and one self-created
registry-to-workflow intersection. Its JSON form is schema-checked by
`schemas/doctor-report-v1.schema.json`:

```bash
starshine doctor --format json
```

## 2. Reproduce the installed core end to end

Run:

```bash
python scripts/reproduce_installed_core.py --output reproduction-report.json
```

The script creates all of its vector inputs and workflow in a temporary directory. It then exercises
the installed console command through this chain:

`doctor → validate → plan → contract → preflight → run → inspect → quality → operators → manifest`

It also executes the same intersection workflow through the public Python API and requires the CLI
and API output digests to match. It does not depend on the tracked examples or on a developer's
working directory. The resulting report can be validated in a development checkout with:

```bash
python scripts/check_reproduction_report.py reproduction-report.json
```

## 3. Run the source verification suite

For a contributor checkout:

```bash
ruff check .
pytest
python scripts/audit_public_repository.py
python scripts/verify_teaching_examples.py
python -m benchmarks.verify
python -m benchmarks.run --repeat 1 --output benchmark-report.json
python scripts/check_benchmark_report.py benchmark-report.json
python -m benchmarks.spatial_index --repeat 1 --output spatial-index-report.json
python scripts/check_spatial_index_benchmark.py spatial-index-report.json
```

Benchmark timing is evidence, not a pass/fail threshold. The semantic signatures and the independent
indexed-versus-exhaustive comparison are the correctness gates.

## 4. Reproduce the built wheel rather than the source checkout

A source test can pass even when a distribution accidentally omits a module or entry point. Build an
artifact and test that exact wheel non-editably:

```bash
python -m pip install -e ".[release]"
python -m build
python -m twine check dist/*
python scripts/check_release_artifacts.py dist
```

Create a second virtual environment and install the wheel there. On macOS or Linux:

```bash
python -m venv .wheel-venv
.wheel-venv/bin/python -m pip install --upgrade pip
.wheel-venv/bin/python -m pip install dist/*.whl
.wheel-venv/bin/python scripts/reproduce_installed_core.py
```

On Windows:

```text
python -m venv .wheel-venv
.wheel-venv\Scripts\python.exe -m pip install --upgrade pip
.wheel-venv\Scripts\python.exe -m pip install dist\starshine_geo-0.4.0-py3-none-any.whl
.wheel-venv\Scripts\python.exe scripts\reproduce_installed_core.py
```

The repository's CI performs the same idea without checking out source code in the installed-wheel
jobs. The exact CI-built wheel is also installed and reproduced on Linux, Windows, and macOS.

## 5. Optional GeoPackage backend

GeoPackage support is intentionally outside the base runtime:

```bash
python -m pip install -e ".[dev,geopackage]"
starshine doctor --require-geopackage
```

When the optional backend is installed, `doctor` creates a temporary package, writes one layer,
lists it, reads it back, and verifies CRS and property preservation. Without
`--require-geopackage`, a missing backend is reported as `SKIP` rather than making the core runtime
unhealthy.

## Interpreting failures

- `package_metadata` failure usually means the code being imported does not match the installed
  distribution metadata.
- `proj` failure indicates a broken or unavailable CRS database / transform runtime.
- `geos` failure indicates the geometry engine cannot complete known exact operations.
- `operator_registry` failure means the installed package has an incomplete reviewed registry.
- `workflow_execution` failure means the registry-to-workflow-to-operator path is not healthy even
  if imports succeed.
- `geopackage_roundtrip` failure is isolated to the optional GeoPackage stack unless it was
  explicitly required.

When opening a bug report, attach the JSON from `starshine doctor --format json` and the JSON from
`reproduce_installed_core.py`. Neither report contains source feature coordinates, property values,
credentials, or working-directory paths.
