from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator

import starshine_geo

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "reproduction-report-v1.schema.json"
EXPECTED_STEPS = [
    "doctor",
    "validate",
    "plan",
    "contract",
    "preflight",
    "run",
    "inspect",
    "quality",
    "operators",
    "manifest",
]


def check(report_path: Path) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)
    if report["starshine_version"] != starshine_geo.__version__:
        raise RuntimeError("reproduction report version does not match installed Starshine")
    if report["reproduced_steps"] != EXPECTED_STEPS:
        raise RuntimeError("reproduction report step order is not canonical")
    print(f"Reproduction report passed schema and semantic checks: {report_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    check(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
