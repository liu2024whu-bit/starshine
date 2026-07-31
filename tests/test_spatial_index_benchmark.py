from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from benchmarks.spatial_index import build_report
from scripts.check_spatial_index_benchmark import check

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "spatial-index-benchmark-v1.schema.json"


def test_spatial_index_report_is_schema_checked_and_semantically_equal(tmp_path):
    tick = 0

    def clock() -> int:
        nonlocal tick
        tick += 1_000_000
        return tick

    report = build_report(repeats=1, clock=clock)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)

    assert [case["name"] for case in report["cases"]] == [
        "join-index-points-1024-zones-256",
        "nearest-index-grid-900-candidates-225",
    ]
    assert [case["exhaustive_pair_count"] for case in report["cases"]] == [
        262144,
        202500,
    ]
    assert all(case["semantic_equal"] for case in report["cases"])
    assert all(case["observed_speedup"] == 1.0 for case in report["cases"])

    report_path = tmp_path / "spatial-index-report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    check(report_path)
