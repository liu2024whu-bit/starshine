# Deterministic small-vector benchmarks

Starshine includes a public benchmark corpus created exclusively from its documented operators and
synthetic geometries. It is intended for repeatable comparisons of small workflow validation and
execution overhead, not for claims about large production datasets.

## Cases

- `buffer-grid-64`: buffers an 8 by 8 projected point grid;
- `dissolve-bands-80`: dissolves 80 adjacent cells into four groups;
- `summarize-zones-16-sites-64`: counts 64 points across 16 zones;
- `multi-step-buffer-dissolve-36`: runs a two-step buffer and dissolve workflow.

The generators live in `benchmarks/corpus.py`. No fixture, parameter set, expected result, or source
implementation is imported from a private repository or external service.

## Verify correctness

Correctness checks are deliberately separate from timing:

```bash
python -m benchmarks.verify
```

They assert feature counts, grouped values, point counts, and output geometry contracts without
setting performance thresholds.

## Run and record observations

```bash
python -m benchmarks.run --repeat 5 --output benchmark-report.json
python scripts/check_benchmark_report.py benchmark-report.json
```

The report records:

- Starshine and Python versions;
- platform metadata;
- input feature, input layer, operation, and output feature counts;
- deterministic corpus, case, and output digests;
- validation-only timing samples;
- validated workflow-run timing samples.

`validated_run` measures the public `run_workflow()` call, which includes Starshine's mandatory
preflight validation. The runner does not attempt to bypass public safety checks to manufacture a
pure execution number.

## Comparing environments

Keep `corpus_version`, `corpus_digest`, each `case_digest`, and `repeat_count` visible when comparing
reports. Timing observations are environment-specific; compare them only alongside Python version,
Starshine version, operating system, machine architecture, and dependency versions. CI validates the
report schema and stable corpus fields but intentionally does not fail on wall-clock thresholds.
