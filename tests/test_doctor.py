from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

import starshine_geo.doctor as doctor_module
from starshine_geo import DOCTOR_REPORT_VERSION, build_doctor_report, render_doctor_text
from starshine_geo.cli import main

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "doctor-report-v1.schema.json"


def test_doctor_report_is_schema_checked_path_free_and_healthy():
    report = build_doctor_report()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)

    assert report["schema_version"] == DOCTOR_REPORT_VERSION == 1
    assert report["valid"] is True
    assert [item["name"] for item in report["checks"][:5]] == [
        "package_metadata",
        "proj",
        "geos",
        "operator_registry",
        "workflow_execution",
    ]
    assert all(item["status"] == "pass" for item in report["checks"][:5])
    payload = json.dumps(report, sort_keys=True)
    assert str(ROOT.resolve()) not in payload


def test_doctor_text_has_compact_runtime_and_check_summary():
    report = build_doctor_report()
    text = render_doctor_text(report)
    assert text.startswith("Starshine doctor: PASS\n")
    assert "Spatial runtime:" in text
    assert "workflow_execution" in text
    assert "geopackage_roundtrip" in text


def test_missing_optional_geopackage_is_skip_unless_required(monkeypatch):
    monkeypatch.setattr(doctor_module, "_distribution_version", lambda name: None)

    optional = build_doctor_report()
    assert optional["valid"] is True
    assert optional["checks"][-1]["status"] == "skip"
    assert optional["optional"]["geopackage"]["available"] is False

    required = build_doctor_report(require_geopackage=True)
    assert required["valid"] is False
    assert required["checks"][-1]["status"] == "fail"


def test_doctor_collects_core_failure_without_hiding_other_checks(monkeypatch):
    def fail_metadata() -> str:
        raise RuntimeError("synthetic metadata failure")

    monkeypatch.setattr(doctor_module, "_metadata_check", fail_metadata)
    report = build_doctor_report()

    assert report["valid"] is False
    assert report["checks"][0] == {
        "name": "package_metadata",
        "status": "fail",
        "detail": "RuntimeError: self-check failed",
    }
    assert report["checks"][1]["status"] == "pass"


def test_doctor_cli_json_and_file_outputs(tmp_path, capsys):
    assert main(["doctor", "--format", "json"]) == 0
    stdout = capsys.readouterr().out
    report = json.loads(stdout)
    assert report["valid"] is True

    output = tmp_path / "doctor.json"
    assert main(["doctor", "--format", "json", "--output", str(output)]) == 0
    assert capsys.readouterr().out.strip() == str(output)
    assert json.loads(output.read_text(encoding="utf-8"))["valid"] is True
