from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.check_reproduction_report import EXPECTED_STEPS, check
from scripts.reproduce_installed_core import build_reproduction_report

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "reproduction-report-v1.schema.json"


def test_self_created_installed_core_reproduction_is_schema_checked(tmp_path):
    report = build_reproduction_report()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)

    assert report["status"] == "ok"
    assert report["doctor_valid"] is True
    assert report["output_feature_count"] == 3
    assert report["reproduced_steps"] == EXPECTED_STEPS

    report_path = tmp_path / "reproduction-report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    check(report_path)
