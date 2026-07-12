# Contributing

Starshine welcomes focused contributions that improve reproducibility, validation, documentation, and small composable geospatial operators.

## Development workflow

1. Open an issue describing the problem, expected behavior, data assumptions, and CRS assumptions.
2. Create a focused branch.
3. Add or update tests for every behavior change.
4. Run `ruff check .` and `pytest`.
5. Open a pull request explaining the GIS semantics, failure boundaries, and reproducibility impact.

## Operator requirements

A new operator must:

- reject missing, empty, or invalid geometry when relevant;
- document input geometry types and CRS requirements;
- validate numeric parameters for finite values and meaningful ranges;
- avoid hidden file-system writes;
- avoid dynamic code execution;
- return a deterministic GeoJSON FeatureCollection;
- include valid and invalid-input tests.

## Data policy

Only self-created, openly licensed, or synthetic data may be committed. Do not commit credentials, private database exports, copyrighted textbooks, OCR derivatives, personal paths, or large generated outputs.
