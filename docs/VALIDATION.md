# Validation record

## Public extraction validation — 2026-07-13

The initial public core was assembled from reviewed concepts and independently tested before publication. Validation used only the files and synthetic data contained in this repository.

Commands:

```bash
PYTHONPATH=src python -m compileall -q src tests examples
PYTHONPATH=src pytest -q
PYTHONPATH=src python examples/run_demo.py
```

Observed results:

- Python compilation completed without errors;
- `7` tests passed;
- the demo produced `examples/output/zone_summary.geojson`;
- expected `site_count` values were `[2, 1]` for the west and east study zones;
- no private dataset, credential, OCR output, textbook PDF, database dump, or machine-specific path was required.

GitHub Actions is the authoritative repeatable check for supported Python versions. Local validation supplements CI and does not replace external reproduction.
