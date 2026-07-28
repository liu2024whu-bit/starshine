import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import starshine_geo.workflow as workflow_module
from starshine_geo import (
    WORKFLOW_PREFLIGHT_VERSION,
    digest_json,
    preflight_workflow_inputs,
    render_workflow_preflight_markdown,
)
from starshine_geo.cli import main
from starshine_geo.errors import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "workflow-preflight-v1.schema.json"
PLAN_WORKFLOW_PATH = ROOT / "examples" / "plan.workflow.json"
SOURCE_PATH = ROOT / "examples" / "data" / "clip-source.geojson"
MASK_PATH = ROOT / "examples" / "data" / "clip-mask.geojson"
MARKDOWN_PATH = ROOT / "examples" / "plan.workflow.preflight.md"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _collection(features, crs="EPSG:3857"):
    value = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        value["starshine:crs"] = crs
    return value


def _point(x, y, **properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [x, y]},
    }


def _square(x, y, size=10, **properties):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]
            ],
        },
    }


def _join_workflow(**parameters):
    values = {"polygon_id_field": "zone_id", **parameters}
    return {
        "version": 1,
        "steps": [
            {
                "operation": "join_points_to_polygons",
                "inputs": {"points": "points", "polygons": "zones"},
                "parameters": values,
                "output": "joined",
            }
        ],
    }


def _finding_codes(report):
    return [finding["code"] for finding in report["findings"]]


def test_preflight_schema_is_valid_and_report_conforms():
    schema = _load(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    report = preflight_workflow_inputs(
        _load(PLAN_WORKFLOW_PATH),
        {"source": _load(SOURCE_PATH), "mask": _load(MASK_PATH), "unused": _collection([])},
    )
    Draft202012Validator(schema).validate(report)
    assert report["schema_version"] == WORKFLOW_PREFLIGHT_VERSION
    assert report["valid"] is True
    assert report["warning_count"] == 1
    assert _finding_codes(report) == ["deferred_crs_equivalence"]


def test_preflight_is_deterministic_and_digest_covers_report_body():
    workflow = _load(PLAN_WORKFLOW_PATH)
    layers = {"source": _load(SOURCE_PATH), "mask": _load(MASK_PATH)}
    first = preflight_workflow_inputs(workflow, layers)
    second = preflight_workflow_inputs(deepcopy(workflow), dict(reversed(list(layers.items()))))
    assert first == second
    body = deepcopy(first)
    digest = body.pop("preflight_digest")
    assert digest == digest_json(body)


def test_preflight_never_executes_registered_operators(monkeypatch):
    def unexpected_execution(inputs, parameters):
        raise AssertionError((inputs, parameters))

    monkeypatch.setitem(workflow_module.OPERATORS, "join_points_to_polygons", unexpected_execution)
    report = preflight_workflow_inputs(
        _join_workflow(),
        {
            "points": _collection([_point(1, 1, name="site")]),
            "zones": _collection([_square(0, 0, zone_id="zone-a")]),
        },
    )
    assert report["valid"] is True


def test_preflight_reports_geometry_fields_and_collisions_without_values():
    report = preflight_workflow_inputs(
        _join_workflow(output_field="zone_id"),
        {
            "points": _collection(
                [
                    _square(0, 0, name="wrong-geometry", zone_id="occupied"),
                    _point(1, 1, name="valid-point", zone_id="occupied"),
                ]
            ),
            "zones": _collection(
                [
                    _square(0, 0, zone_id="duplicate"),
                    _square(20, 0, zone_id="duplicate"),
                    _square(40, 0),
                ]
            ),
        },
    )

    assert report["valid"] is False
    assert set(_finding_codes(report)) == {
        "unsupported_geometry_type",
        "output_field_collision",
        "duplicate_required_field",
        "missing_required_field",
    }
    collision = next(item for item in report["findings"] if item["code"] == "output_field_collision")
    assert collision["occurrence_count"] == 2
    assert collision["feature_indexes"] == [0, 1]
    serialized = json.dumps(report)
    assert '"duplicate"' not in serialized
    assert '"occupied"' not in serialized


def test_preflight_reports_crs_rules_and_equivalence():
    workflow = _join_workflow()
    missing = preflight_workflow_inputs(
        workflow,
        {
            "points": _collection([_point(1, 1)], crs=None),
            "zones": _collection([_square(0, 0, zone_id="a")]),
        },
    )
    assert "missing_declared_crs" in _finding_codes(missing)

    mismatch = preflight_workflow_inputs(
        workflow,
        {
            "points": _collection([_point(1, 1)], crs="EPSG:3857"),
            "zones": _collection([_square(0, 0, zone_id="a")], crs="EPSG:32650"),
        },
    )
    assert _finding_codes(mismatch).count("crs_mismatch") == 1


def test_preflight_reports_projected_and_parameter_crs_requirements():
    metrics_workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "geometry_metrics",
                "inputs": {"input": "features"},
                "parameters": {},
                "output": "measured",
            }
        ],
    }
    geographic = preflight_workflow_inputs(
        metrics_workflow,
        {"features": _collection([_point(0, 0)], crs="EPSG:4326")},
    )
    assert "non_projected_crs" in _finding_codes(geographic)

    buffer_workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "buffer",
                "inputs": {"input": "sites"},
                "parameters": {
                    "distance": 5,
                    "source_crs": "EPSG:3857",
                    "work_crs": "EPSG:3857",
                },
                "output": "buffers",
            }
        ],
    }
    conflict = preflight_workflow_inputs(
        buffer_workflow,
        {"sites": _collection([_point(0, 0)], crs="EPSG:4326")},
    )
    assert "declared_crs_conflicts_parameter" in _finding_codes(conflict)


def test_preflight_reports_duplicate_resolved_output_fields():
    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "geometry_metrics",
                "inputs": {"input": "features"},
                "parameters": {"area_field": "metric", "length_field": "metric"},
                "output": "measured",
            }
        ],
    }
    report = preflight_workflow_inputs(
        workflow,
        {"features": _collection([_square(0, 0)])},
    )
    assert "duplicate_output_field" in _finding_codes(report)


def test_preflight_aggregates_invalid_feature_collection_failure():
    invalid = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": None}],
    }
    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "dissolve",
                "inputs": {"input": "source"},
                "parameters": {},
                "output": "result",
            }
        ],
    }
    report = preflight_workflow_inputs(workflow, {"source": invalid})
    assert report["valid"] is False
    assert report["layers"][0]["status"] == "failed"
    assert _finding_codes(report) == ["invalid_feature_collection"]


def test_preflight_markdown_matches_tracked_example():
    report = preflight_workflow_inputs(
        _load(PLAN_WORKFLOW_PATH),
        {"source": _load(SOURCE_PATH), "mask": _load(MASK_PATH), "unused": _collection([])},
    )
    markdown = render_workflow_preflight_markdown(report)
    assert markdown == MARKDOWN_PATH.read_text(encoding="utf-8")
    assert "Status: **PASS**" in markdown
    assert "deferred_crs_equivalence" in markdown


def test_preflight_renderer_rejects_malformed_reports():
    with pytest.raises(ValidationError, match="schema version 1"):
        render_workflow_preflight_markdown({"schema_version": 2})
    with pytest.raises(ValidationError, match="layers array"):
        render_workflow_preflight_markdown({"schema_version": 1, "findings": []})


def test_preflight_cli_prints_json_and_uses_distinct_exit_codes(tmp_path, capsys):
    result = main(
        [
            "preflight",
            str(PLAN_WORKFLOW_PATH),
            "--layer",
            f"source={SOURCE_PATH}",
            "--layer",
            f"mask={MASK_PATH}",
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    assert result == 0
    assert json.loads(captured.out)["valid"] is True
    assert captured.err == ""

    bad_points = tmp_path / "points.geojson"
    zones = tmp_path / "zones.geojson"
    workflow = tmp_path / "join.workflow.json"
    bad_points.write_text(json.dumps(_collection([_square(0, 0)])), encoding="utf-8")
    zones.write_text(json.dumps(_collection([_square(0, 0, zone_id="a")])), encoding="utf-8")
    workflow.write_text(json.dumps(_join_workflow()), encoding="utf-8")
    assert (
        main(
            [
                "preflight",
                str(workflow),
                "--layer",
                f"points={bad_points}",
                "--layer",
                f"zones={zones}",
            ]
        )
        == 1
    )
    assert "Status: **FAIL**" in capsys.readouterr().out


def test_preflight_cli_rejects_overwriting_workflow_or_input(tmp_path, capsys):
    workflow = tmp_path / "workflow.json"
    source = tmp_path / "source.geojson"
    workflow.write_text(PLAN_WORKFLOW_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    source.write_text(SOURCE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    assert (
        main(
            [
                "preflight",
                str(workflow),
                "--layer",
                f"source={source}",
                "--layer",
                f"mask={MASK_PATH}",
                "--output",
                str(source),
            ]
        )
        == 2
    )
    assert "must not overwrite an input layer" in capsys.readouterr().err
