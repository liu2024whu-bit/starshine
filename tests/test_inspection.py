import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from starshine_geo import digest_json, inspect_feature_collection
from starshine_geo.cli import main
from starshine_geo.errors import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "inspection-report-v1.schema.json"


def _mixed_collection():
    return {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:3857",
        "features": [
            {
                "type": "Feature",
                "properties": {"id": "site-1", "name": "sample"},
                "geometry": {"type": "Point", "coordinates": [1, 2]},
            },
            {
                "type": "Feature",
                "properties": {"id": "zone-1", "category": "study"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [4, 0], [4, 3], [0, 3], [0, 0]]],
                },
            },
        ],
    }


def test_inspection_reports_deterministic_public_structure():
    collection = _mixed_collection()

    report = inspect_feature_collection(collection)

    assert report == {
        "schema_version": 1,
        "collection_digest": digest_json(collection),
        "feature_count": 2,
        "geometry_counts": {"Point": 1, "Polygon": 1},
        "property_fields": ["category", "id", "name"],
        "declared_crs": "EPSG:3857",
        "bbox": [0.0, 0.0, 4.0, 3.0],
    }
    serialized_report = json.dumps(report, sort_keys=True)
    assert "sample" not in serialized_report
    assert "site-1" not in serialized_report
    assert "zone-1" not in serialized_report

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(report)


def test_inspection_supports_empty_valid_collection():
    report = inspect_feature_collection({"type": "FeatureCollection", "features": []})

    assert report["feature_count"] == 0
    assert report["geometry_counts"] == {}
    assert report["property_fields"] == []
    assert report["declared_crs"] is None
    assert report["bbox"] is None


def test_inspection_rejects_topologically_invalid_geometry():
    invalid = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [2, 2], [0, 2], [2, 0], [0, 0]]],
                },
            }
        ],
    }

    with pytest.raises(ValidationError, match="topologically invalid"):
        inspect_feature_collection(invalid)


def test_inspect_cli_prints_report_and_writes_identical_output(tmp_path, capsys):
    collection = _mixed_collection()
    source = tmp_path / "mixed.geojson"
    output = tmp_path / "mixed.inspection.json"
    source.write_text(json.dumps(collection), encoding="utf-8")

    result = main(["inspect", str(source)])
    captured = capsys.readouterr()

    assert result == 0
    stdout_report = json.loads(captured.out)
    assert stdout_report == inspect_feature_collection(collection)
    assert captured.err == ""

    result = main(["inspect", str(source), "--output", str(output)])
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out.strip() == str(output)
    assert captured.err == ""
    assert json.loads(output.read_text(encoding="utf-8")) == stdout_report


def test_inspect_cli_emits_json_error_envelope(tmp_path, capsys):
    source = tmp_path / "invalid.geojson"
    source.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {"type": "Point", "coordinates": []},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = main(["inspect", str(source), "--diagnostic-format", "json"])
    captured = capsys.readouterr()

    assert result == 2
    assert captured.out == ""
    envelope = json.loads(captured.err)
    assert envelope["error"] == "starshine_error"
    assert "invalid geometry" in envelope["message"] or "empty geometry" in envelope["message"]


def test_inspect_cli_does_not_overwrite_source(tmp_path, capsys):
    collection = _mixed_collection()
    source = tmp_path / "mixed.geojson"
    original = json.dumps(collection)
    source.write_text(original, encoding="utf-8")

    result = main(
        [
            "inspect",
            str(source),
            "--output",
            str(source),
            "--diagnostic-format",
            "json",
        ]
    )
    captured = capsys.readouterr()

    assert result == 2
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "error": "starshine_error",
        "message": "inspection output must not overwrite the source GeoJSON",
    }
    assert source.read_text(encoding="utf-8") == original
