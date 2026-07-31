from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

import starshine_geo
from starshine_geo import digest_json

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "spatial-index-benchmark-v1.schema.json"
EXPECTED_NAMES = [
    "join-index-points-1024-zones-256",
    "nearest-index-grid-900-candidates-225",
]


def _expected_cases():
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from benchmarks.corpus import build_cases

    return {case.name: case for case in build_cases()}


def check(report_path: Path) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)

    if report["starshine_version"] != starshine_geo.__version__:
        raise RuntimeError("spatial-index report version does not match installed Starshine")
    names = [case["name"] for case in report["cases"]]
    if names != EXPECTED_NAMES:
        raise RuntimeError(f"unexpected spatial-index case order: {names}")

    definitions = _expected_cases()
    for item in report["cases"]:
        case = definitions[item["name"]]
        expected_digest = digest_json(case.expected_signature)
        if item["semantic_digest"] != expected_digest:
            raise RuntimeError(f"{case.name}: indexed semantic digest mismatch")
        if item["reference_semantic_digest"] != expected_digest:
            raise RuntimeError(f"{case.name}: reference semantic digest mismatch")
        if item["exhaustive_pair_count"] != (
            item["source_feature_count"] * item["candidate_feature_count"]
        ):
            raise RuntimeError(f"{case.name}: exhaustive pair count is inconsistent")

    print(f"Spatial-index benchmark passed schema and semantic checks: {report_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    check(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
