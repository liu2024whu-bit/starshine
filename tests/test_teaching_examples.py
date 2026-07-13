from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from starshine_geo import inspect_feature_collection, run_workflow, validate_workflow
from starshine_geo.errors import ValidationError, WorkflowValidationError

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "teaching"
INSPECTION_SCHEMA = ROOT / "schemas" / "inspection-report-v1.schema.json"


def _read_json(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def test_projected_teaching_inspection_matches_reviewable_expected_report():
    collection = _read_json("projected-points.geojson")
    expected = _read_json("projected-points.inspection.json")

    report = inspect_feature_collection(collection)

    assert report == expected
    schema = json.loads(INSPECTION_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(report)


def test_corrected_projected_buffer_has_stable_semantic_structure():
    workflow = _read_json("buffer-projected-valid.workflow.json")
    points = _read_json("projected-points.geojson")

    validate_workflow(workflow, {"points"})
    result = run_workflow(workflow, {"points": points})
    report = inspect_feature_collection(result["buffers"])

    assert report["feature_count"] == 3
    assert report["geometry_counts"] == {"Polygon": 3}
    assert report["property_fields"] == [
        "id",
        "starshine:buffer_distance",
        "starshine:work_crs",
    ]
    assert report["declared_crs"] == "EPSG:3857"
    assert report["bbox"] == [-25.0, -25.0, 225.0, 125.0]


def test_geographic_work_crs_example_has_stable_diagnostic_path():
    workflow = _read_json("buffer-geographic-invalid.workflow.json")

    with pytest.raises(WorkflowValidationError) as exc_info:
        validate_workflow(workflow, {"points"})

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.code == "invalid_parameter"
    assert diagnostic.path == "steps[0].parameters.work_crs"
    assert diagnostic.step_index == 0
    assert diagnostic.operation == "buffer"
    assert "projected CRS with linear units" in diagnostic.message


@pytest.mark.parametrize(
    ("filename", "message"),
    [
        ("self-intersecting-polygon.geojson", "topologically invalid geometry"),
        ("empty-polygon.geojson", "empty geometry"),
        ("malformed-properties.geojson", "properties must be an object or null"),
    ],
)
def test_invalid_teaching_geojson_is_rejected(filename: str, message: str):
    with pytest.raises(ValidationError, match=message):
        inspect_feature_collection(_read_json(filename))


def test_public_teaching_verifier_runs_the_documented_cli_contracts():
    result = subprocess.run(
        [sys.executable, "scripts/verify_teaching_examples.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Verified six synthetic CRS and geometry teaching checks."
