# Architecture

Starshine uses a deliberately small modular architecture.

- `geojson.py` validates and normalizes the public data contract.
- `inspection.py` produces deterministic collection-level reports after validation.
- `crs.py` centralizes CRS parsing, projected-coordinate requirements, and transforms.
- `operators.py` implements independently testable transformation, overlay, attribution, summary,
  and proximity operations.
- `operator_registry.py` binds reviewed executors to public input, parameter, default, and sensitivity contracts.
- `workflow.py` maps versioned JSON steps to an explicit operator registry.
- `planning.py` produces deterministic data-free dependency and layer-provenance reports.
- `cli.py` provides reproducible file-based execution.

The workflow layer does not import functions from arbitrary module names and does not use `eval`, `exec`, shell commands, or user-provided Python. Each operator returns an in-memory FeatureCollection; the CLI is the only component that writes a selected result to disk.

## Design principles

1. **GIS semantics before convenience.** Distance work must declare a projected CRS.
2. **Small operators.** Each operation has one independently testable responsibility.
3. **Declarative extension.** Runtime execution, defaults, parameter validation, planning, and catalog metadata share one reviewed registry entry.
4. **Explicit failure.** Invalid geometry, missing fields, and unsupported operations fail with actionable errors.
5. **Reproducibility.** A workflow, named inputs, package version, and output layer are sufficient to repeat the included demo.
6. **Public/private separation.** Experimental modules and unreleased data do not silently leak into the public core.
7. **Teaching artifacts stay external to runtime.** Intentional failures live under `examples/teaching/` and exercise public contracts without becoming package dependencies.
