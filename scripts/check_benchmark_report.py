from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

import starshine_geo
from starshine_geo import digest_json

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "benchmark-report-v1.schema.json"


def _build_cases():
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from benchmarks.corpus import build_cases

    return build_cases()


def check(report_path: Path) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(report)

    cases = _build_cases()
    expected_definitions = [case.definition() for case in cases]
    expected_names = [case.name for case in cases]
    actual_names = [item["name"] for item in report["cases"]]

    if actual_names != expected_names:
        raise RuntimeError(f"unexpected benchmark case order: {actual_names}")
    if report["corpus_digest"] != digest_json(expected_definitions):
        raise RuntimeError("benchmark corpus digest does not match the public case definitions")
    if report["starshine_version"] != starshine_geo.__version__:
        raise RuntimeError(
            "benchmark report version does not match the installed Starshine version"
        )

    for case, item in zip(cases, report["cases"], strict=True):
        expected: dict[str, Any] = {
            "case_digest": digest_json(case.definition()),
            "semantic_digest": digest_json(case.expected_signature),
            "input_layer_count": len(case.layers),
            "input_feature_count": case.input_feature_count,
            "operation_count": case.operation_count,
            "output_layer": case.output_layer,
        }
        for key, value in expected.items():
            if item[key] != value:
                raise RuntimeError(f"{case.name}: unexpected {key}: {item[key]!r}")

    print(f"Benchmark report passed schema and corpus checks: {report_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    check(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
