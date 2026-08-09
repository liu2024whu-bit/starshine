# Deterministic vector benchmarks

Starshine includes a public benchmark corpus created exclusively from documented operators and
synthetic geometries. It is intended for reproducible semantic and timing comparisons, not for
unqualified production-throughput claims.

## Corpus cases

- `buffer-grid-64`: buffers an 8 by 8 projected point grid;
- `dissolve-bands-80`: dissolves 80 adjacent cells into four groups;
- `geometry-metrics-grid-25`: measures area and boundary length for 25 projected squares;
- `summarize-zones-16-sites-64`: counts 64 points across 16 zones;
- `multi-step-buffer-dissolve-36`: runs a two-step buffer and dissolve workflow;
- `clip-grid-25`: clips a 5 by 5 polygon grid with one offset polygon mask;
- `intersection-index-parcels-1600-zones-400`: intersects 1,600 parcels with 400 separated planning zones across 640,000 exhaustive pairs;
- `nearest-grid-36-candidates-9`: matches 36 source points to nine candidates with stable ties;
- `join-points-64-zones-16`: attributes 64 points to 16 non-overlapping polygon zones;
- `join-index-points-1024-zones-256`: exercises indexed attribution across 262,144 possible pairs;
- `nearest-index-grid-900-candidates-225`: exercises indexed nearest matching across 202,500
  possible pairs.

The generators live in `benchmarks/corpus.py`. No fixture, parameter set, expected result, or source
implementation is imported from a private repository or external service.

## Verify correctness

Correctness checks are deliberately separate from timing:

```bash
python -m benchmarks.verify
```

They compare representation-independent semantic signatures for feature counts, grouped values,
point counts, CRS values, assignments, nearest matches, and documented operator metadata.

## Run the complete public corpus

```bash
python -m benchmarks.run --repeat 5 --output benchmark-report.json
python scripts/check_benchmark_report.py benchmark-report.json
```

The report records:

- Starshine and Python versions;
- platform metadata;
- input feature, input layer, operation, and output feature counts;
- deterministic corpus and case digests;
- stable semantic and raw output digests;
- validation-only and validated workflow-run timing samples.

`validated_run` measures the public `run_workflow()` call, including mandatory workflow validation.
The runner does not bypass public safety checks to manufacture a pure execution number.

Raw geometry serialization can legitimately differ across Shapely or GEOS versions even when the
semantic result is equivalent. Use `semantic_digest` for correctness comparisons. Treat
`output_digest` as an additional representation observation.

## Compare STRtree and exhaustive references

The focused spatial-index benchmark runs the three larger indexed cases through both the public API
and an independent exhaustive implementation:

```bash
python -m benchmarks.spatial_index --repeat 5 --output spatial-index-report.json
python scripts/check_spatial_index_benchmark.py spatial-index-report.json
```

The schema-checked report records:

- Starshine, Shapely, Python, operating-system, and machine metadata;
- source and candidate counts plus the exhaustive pair count;
- indexed and reference semantic digests, which must be equal;
- timing samples for both paths;
- an observed speedup ratio.

The checker requires semantic equality and corpus consistency. It intentionally does not require a
minimum wall-clock speedup because shared CI machines, Python, Shapely, GEOS, and geometry layout all
affect timing. This keeps performance evidence visible without converting runner noise into a false
correctness failure.

## Comparing environments

The current public corpus version is `7`. Keep `corpus_version`, `corpus_digest`, each `case_digest`,
each `semantic_digest`, and `repeat_count` visible when comparing corpus reports. For spatial-index
reports, also retain `shapely_version`, exhaustive pair counts, and both timing series. Compare timing
only alongside the recorded environment.
