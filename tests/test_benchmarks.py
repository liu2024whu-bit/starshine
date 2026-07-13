import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from benchmarks.corpus import build_cases
from benchmarks.run import build_report
from benchmarks.verify import verify_case
from starshine_geo import digest_json

ROOT = Path(__file__).parents[1]
SCHEMA_PATH = ROOT / "schemas" / "benchmark-report-v1.schema.json"


def test_public_benchmark_corpus_is_deterministic():
    first = build_cases()
    second = build_cases()

    assert [case.name for case in first] == [
        "buffer-grid-64",
        "dissolve-bands-80",
        "summarize-zones-16-sites-64",
        "multi-step-buffer-dissolve-36",
    ]
    assert digest_json([case.definition() for case in first]) == digest_json(
        [case.definition() for case in second]
    )
    assert [case.input_feature_count for case in first] == [64, 80, 80, 36]
    assert [case.operation_count for case in first] == [1, 1, 1, 2]


def test_benchmark_correctness_checks_are_separate_from_timing():
    for case in build_cases():
        verify_case(case)


def test_benchmark_report_matches_public_schema_with_deterministic_clock():
    tick = 0

    def clock() -> int:
        nonlocal tick
        tick += 1_000_000
        return tick

    report = build_report(repeats=2, clock=clock)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(report)

    cases = build_cases()
    assert report["repeat_count"] == 2
    assert [case["output_feature_count"] for case in report["cases"]] == [64, 4, 16, 1]
    assert [case["semantic_digest"] for case in report["cases"]] == [
        digest_json(case.expected_signature) for case in cases
    ]
    for case in report["cases"]:
        assert case["timing"]["validation_only"]["samples_seconds"] == pytest.approx(
            [0.001, 0.001], rel=0, abs=1e-12
        )
        assert case["timing"]["validated_run"]["samples_seconds"] == pytest.approx(
            [0.001, 0.001], rel=0, abs=1e-12
        )


def test_benchmark_semantic_digests_repeat_in_the_same_environment():
    first = build_report(repeats=1)
    second = build_report(repeats=1)

    assert [case["semantic_digest"] for case in first["cases"]] == [
        case["semantic_digest"] for case in second["cases"]
    ]
