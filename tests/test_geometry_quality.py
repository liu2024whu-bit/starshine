import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import starshine_geo._geometry_quality_report as quality_report_module
from starshine_geo import (
    GEOMETRY_QUALITY_REPORT_VERSION,
    assess_geometry_quality,
    digest_json,
    render_geometry_quality_markdown,
)
from starshine_geo.cli import main
from starshine_geo.errors import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "examples" / "geometry-quality.geojson"
REPORT_PATH = ROOT / "examples" / "geometry-quality.report.json"
MARKDOWN_PATH = ROOT / "examples" / "geometry-quality.report.md"
SCHEMA_PATH = ROOT / "schemas" / "geometry-quality-report-v1.schema.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _point_collection(*, crs="EPSG:3857"):
    value = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "not-in-report"},
                "geometry": {"type": "Point", "coordinates": [1, 2]},
            }
        ],
    }
    if crs is not None:
        value["starshine:crs"] = crs
    return value


def test_example_is_schema_checked_deterministic_and_private():
    collection = _load(SOURCE_PATH)
    report = assess_geometry_quality(collection)
    schema = _load(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(report)

    inconsistent = deepcopy(report)
    inconsistent["collection_digest_status"] = "unavailable"
    assert list(validator.iter_errors(inconsistent))

    assert report == _load(REPORT_PATH)
    assert report["schema_version"] == GEOMETRY_QUALITY_REPORT_VERSION
    assert report["collection_digest_status"] == "available"
    assert report["feature_count"] == 5
    assert report["parsed_geometry_count"] == 5
    assert report["valid_geometry_count"] == 3
    assert report["invalid_geometry_count"] == 2
    assert report["geometry_counts"] == {"LineString": 1, "Point": 2, "Polygon": 2}
    assert report["coordinate_dimension_counts"] == {
        "2D": 3,
        "3D": 1,
        "mixed": 0,
        "unsupported": 0,
        "unknown": 1,
    }
    assert report["duplicate_geometry_group_count"] == 1
    assert report["duplicate_feature_count"] == 2
    assert report["error_count"] == 2
    assert report["warning_count"] == 3
    assert report["valid"] is False

    body = deepcopy(report)
    assert body.pop("quality_digest") == digest_json(body)
    assert report == assess_geometry_quality(deepcopy(collection))
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
    for private_value in ("private-site-a", "private-bowtie", "[1 1]", '"coordinates"'):
        assert private_value not in serialized


def test_markdown_matches_tracked_example_and_is_private():
    markdown = render_geometry_quality_markdown(assess_geometry_quality(_load(SOURCE_PATH)))
    assert markdown == MARKDOWN_PATH.read_text(encoding="utf-8")
    assert "Self-intersection" in markdown
    assert "private-site-a" not in markdown
    assert "[1 1]" not in markdown


def test_structural_coordinate_and_non_json_failures_are_aggregated():
    collection = {
        "type": "FeatureCollection",
        "starshine:crs": "not-a-crs",
        "features": [
            "not-a-feature",
            {"type": "Feature", "properties": {}, "geometry": None},
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Point", "coordinates": [1]},
            },
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Point", "coordinates": [1, float("nan")]},
            },
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Point", "coordinates": [1, 2, 3, 4]},
            },
        ],
    }
    report = assess_geometry_quality(collection)
    assert [item["code"] for item in report["findings"]] == [
        "non_json_collection",
        "invalid_declared_crs",
        "invalid_feature",
        "missing_geometry",
        "invalid_coordinate",
        "unsupported_coordinate_dimension",
        "non_finite_coordinate",
    ]
    assert report["collection_digest"] is None
    assert report["collection_digest_status"] == "unavailable"
    assert report["declared_crs"] is None
    assert report["invalid_geometry_count"] == 5
    assert report["parsed_geometry_count"] == 0
    assert report["coordinate_dimension_counts"] == {
        "2D": 1,
        "3D": 0,
        "mixed": 0,
        "unsupported": 2,
        "unknown": 2,
    }
    assert next(item for item in report["findings"] if item["code"] == "invalid_coordinate")[
        "feature_indexes"
    ] == [2]
    assert next(item for item in report["findings"] if item["code"] == "non_finite_coordinate")[
        "feature_indexes"
    ] == [3]
    json.dumps(report, allow_nan=False)


def test_warning_only_report_stays_valid():
    collection = _point_collection(crs=None)
    collection["features"].append(deepcopy(collection["features"][0]))
    report = assess_geometry_quality(collection)
    assert report["valid"] is True
    assert report["error_count"] == 0
    assert report["warning_count"] == 3
    assert [item["code"] for item in report["findings"]] == [
        "missing_declared_crs",
        "duplicate_geometry",
    ]


def test_malformed_inputs_and_renderer_contract_are_rejected():
    with pytest.raises(ValidationError, match="FeatureCollection"):
        assess_geometry_quality({"type": "Feature"})
    with pytest.raises(ValidationError, match="features must be a list"):
        assess_geometry_quality({"type": "FeatureCollection", "features": {}})
    with pytest.raises(ValidationError, match="schema version 1"):
        render_geometry_quality_markdown({"schema_version": 2})
    with pytest.raises(ValidationError, match="findings array"):
        render_geometry_quality_markdown({"schema_version": 1, "geometry_counts": {}})
    malformed = {
        "schema_version": 1,
        "geometry_counts": {},
        "findings": [],
        "collection_digest_status": "available",
        "collection_digest": None,
    }
    with pytest.raises(ValidationError, match="available collection digests"):
        render_geometry_quality_markdown(malformed)


def test_cli_formats_exit_codes_nonfinite_and_overwrite_guard(tmp_path, capsys):
    source = tmp_path / "quality.geojson"
    json_output = tmp_path / "quality.report.json"
    markdown_output = tmp_path / "quality.report.md"
    source.write_text(SOURCE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    assert main(["quality", str(source), "--format", "json"]) == 1
    assert json.loads(capsys.readouterr().out) == _load(REPORT_PATH)
    assert main(["quality", str(source), "--format", "json", "--output", str(json_output)]) == 1
    assert capsys.readouterr().out.strip() == str(json_output)
    assert json.loads(json_output.read_text(encoding="utf-8")) == _load(REPORT_PATH)
    assert main(["quality", str(source), "--output", str(markdown_output)]) == 1
    assert capsys.readouterr().out.strip() == str(markdown_output)
    assert markdown_output.read_text(encoding="utf-8") == MARKDOWN_PATH.read_text(encoding="utf-8")
    assert main(["quality", str(source), "--output", str(source)]) == 2
    assert "must not overwrite" in capsys.readouterr().err

    valid = tmp_path / "valid.geojson"
    valid.write_text(json.dumps(_point_collection(crs=None)), encoding="utf-8")
    assert main(["quality", str(valid), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True

    non_finite = tmp_path / "non-finite.geojson"
    data = _point_collection()
    data["features"][0]["geometry"]["coordinates"] = [1, float("nan")]
    non_finite.write_text(json.dumps(data), encoding="utf-8")
    assert main(["quality", str(non_finite), "--format", "json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["collection_digest"] is None
    assert report["collection_digest_status"] == "unavailable"
    assert "non_finite_coordinate" in {item["code"] for item in report["findings"]}

    missing = tmp_path / "missing.geojson"
    assert main(["quality", str(missing), "--diagnostic-format", "json"]) == 2
    envelope = json.loads(capsys.readouterr().err)
    assert envelope["error"] == "starshine_error"
    assert "File not found" in envelope["message"]


def test_input_is_not_mutated_and_non_json_properties_remain_private():
    collection = _point_collection()
    collection["features"][0]["properties"]["private"] = {"not", "json"}
    before = deepcopy(collection)
    report = assess_geometry_quality(collection)
    assert collection == before
    assert report["collection_digest"] is None
    assert report["collection_digest_status"] == "unavailable"
    assert report["valid"] is False
    assert report["invalid_geometry_count"] == 0
    assert [item["code"] for item in report["findings"]] == ["non_json_collection"]
    assert "private" not in json.dumps(report, sort_keys=True)


def test_duplicate_normalization_is_orientation_invariant_and_dimension_sensitive():
    collection = {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:3857",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            },
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "LineString", "coordinates": [[1, 1], [0, 0]]},
            },
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[0, 0, 1], [1, 1, 1]],
                },
            },
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[0, 0, 2], [1, 1, 2]],
                },
            },
        ],
    }
    report = assess_geometry_quality(collection)
    assert report["duplicate_geometry_group_count"] == 1
    assert report["duplicate_feature_count"] == 2
    duplicate = next(item for item in report["findings"] if item["code"] == "duplicate_geometry")
    assert duplicate["feature_indexes"] == [0, 1]


def test_geometry_collection_dimensions_and_finding_samples_are_bounded_unique():
    collection = {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:3857",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "GeometryCollection",
                    "geometries": [
                        {"type": "Point", "coordinates": [0, 0]},
                        {"type": "LineString", "coordinates": [[0, 0, 1], [1, 1, 1]]},
                    ],
                },
            },
            *[
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {"type": "Point", "coordinates": [5, 5]},
                }
                for _ in range(25)
            ],
        ],
    }
    report = assess_geometry_quality(collection)
    assert report["coordinate_dimension_counts"]["mixed"] == 1
    assert "mixed_coordinate_dimensions" in {item["code"] for item in report["findings"]}
    duplicate = next(item for item in report["findings"] if item["code"] == "duplicate_geometry")
    assert duplicate["occurrence_count"] == 25
    assert duplicate["feature_indexes"] == list(range(1, 21))


def test_invalid_type_and_crs_values_are_redacted():
    secret = "private/customer/project/path"
    collection = {
        "type": "FeatureCollection",
        "starshine:crs": secret,
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": secret, "coordinates": [1, 2]},
            }
        ],
    }
    report = assess_geometry_quality(collection)
    serialized = json.dumps(report, sort_keys=True)
    assert secret not in serialized
    assert report["declared_crs"] is None
    assert report["crs_status"] == "invalid"
    finding = next(item for item in report["findings"] if item["code"] == "unparseable_geometry")
    assert finding["geometry_type"] == "Unknown"


def test_unexpected_programming_errors_are_not_hidden(monkeypatch):
    def unexpected(_value):
        raise RuntimeError("programming defect")

    monkeypatch.setattr(quality_report_module, "shape", unexpected)
    with pytest.raises(RuntimeError, match="programming defect"):
        assess_geometry_quality(_point_collection())
