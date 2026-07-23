import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import starshine_geo.workflow as workflow_module
from starshine_geo import (
    WORKFLOW_CONTRACT_VERSION,
    build_workflow_contract,
    digest_json,
    render_workflow_contract_markdown,
)
from starshine_geo.cli import main
from starshine_geo.errors import ValidationError

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_SCHEMA_PATH = ROOT / "schemas" / "workflow-contract-v1.schema.json"
PLAN_WORKFLOW_PATH = ROOT / "examples" / "plan.workflow.json"
MARKDOWN_EXAMPLE_PATH = ROOT / "examples" / "plan.workflow.contract.md"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _single_step(operation, inputs, parameters, output="result"):
    return {
        "version": 1,
        "steps": [
            {
                "operation": operation,
                "inputs": inputs,
                "parameters": parameters,
                "output": output,
            }
        ],
    }


def _layer(report, name):
    return next(item for item in report["layers"] if item["name"] == name)


def test_workflow_contract_schema_is_valid_and_report_conforms():
    schema = _load(CONTRACT_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    report = build_workflow_contract(
        _load(PLAN_WORKFLOW_PATH), {"source", "mask", "unused"}
    )
    Draft202012Validator(schema).validate(report)
    assert report["schema_version"] == WORKFLOW_CONTRACT_VERSION


def test_contract_reuses_plan_provenance_and_describes_external_layers():
    report = build_workflow_contract(
        _load(PLAN_WORKFLOW_PATH), ["unused", "mask", "source"]
    )

    assert report["required_external_layers"] == ["mask", "source"]
    assert report["unused_external_layers"] == ["unused"]
    assert report["layer_count"] == 3

    source_use = _layer(report, "source")["uses"][0]
    assert source_use == {
        "step_index": 0,
        "operation": "reproject",
        "input_name": "input",
        "geometry_types": [],
        "crs": {"mode": "declared"},
        "required_fields": [],
        "written_fields": [],
        "notes": [],
    }

    mask_use = _layer(report, "mask")["uses"][0]
    assert mask_use["geometry_types"] == ["Polygon", "MultiPolygon"]
    assert mask_use["crs"] == {
        "mode": "declared",
        "equivalent_to_layer": "projected",
    }
    assert _layer(report, "unused") == {
        "name": "unused",
        "required": False,
        "unused": True,
        "use_count": 0,
        "uses": [],
    }


def test_contract_resolves_nearest_field_and_crs_requirements():
    workflow = _single_step(
        "nearest",
        {"source": "sites", "candidates": "facilities"},
        {"candidate_id_field": "facility_id"},
    )
    report = build_workflow_contract(workflow, {"sites", "facilities"})

    source = _layer(report, "sites")["uses"][0]
    assert source["crs"] == {
        "mode": "projected",
        "equivalent_to_layer": "facilities",
    }
    assert source["written_fields"] == [
        {
            "name": "nearest_id",
            "source_parameter": "nearest_id_field",
            "collision_policy": "reject",
        },
        {
            "name": "nearest_distance",
            "source_parameter": "distance_field",
            "collision_policy": "reject",
        },
    ]

    candidates = _layer(report, "facilities")["uses"][0]
    assert candidates["required_fields"] == [
        {
            "name": "facility_id",
            "source_parameter": "candidate_id_field",
            "unique": True,
            "non_null": True,
            "finite_json_scalar": True,
        }
    ]


def test_contract_describes_join_metrics_buffer_and_summary_policies():
    join = build_workflow_contract(
        _single_step(
            "join_points_to_polygons",
            {"points": "points", "polygons": "zones"},
            {"polygon_id_field": "zone_id", "output_field": "zone"},
        ),
        {"points", "zones"},
    )
    assert _layer(join, "points")["uses"][0]["geometry_types"] == ["Point"]
    assert _layer(join, "zones")["uses"][0]["geometry_types"] == [
        "Polygon",
        "MultiPolygon",
    ]
    assert _layer(join, "zones")["uses"][0]["required_fields"][0]["name"] == "zone_id"
    assert _layer(join, "points")["uses"][0]["written_fields"][0]["name"] == "zone"

    metrics = build_workflow_contract(
        _single_step("geometry_metrics", {"input": "features"}, {}),
        {"features"},
    )
    metric_use = _layer(metrics, "features")["uses"][0]
    assert metric_use["crs"] == {"mode": "projected"}
    assert [item["name"] for item in metric_use["written_fields"]] == [
        "geometry_area",
        "geometry_length",
    ]

    buffer = build_workflow_contract(
        _single_step(
            "buffer",
            {"input": "sites"},
            {
                "distance": 5,
                "source_crs": "EPSG:4326",
                "work_crs": "EPSG:3857",
            },
        ),
        {"sites"},
    )
    buffer_use = _layer(buffer, "sites")["uses"][0]
    assert buffer_use["crs"] == {
        "mode": "parameter",
        "parameter": "source_crs",
        "value": "EPSG:4326",
    }
    assert [item["collision_policy"] for item in buffer_use["written_fields"]] == [
        "overwrite",
        "overwrite",
    ]

    summary = build_workflow_contract(
        _single_step(
            "summarize_points_within",
            {"polygons": "zones", "points": "sites"},
            {},
        ),
        {"zones", "sites"},
    )
    assert _layer(summary, "zones")["uses"][0]["required_fields"][0]["name"] == "id"
    assert _layer(summary, "zones")["uses"][0]["written_fields"][0] == {
        "name": "point_count",
        "source_parameter": "count_field",
        "collision_policy": "overwrite",
    }
    assert _layer(summary, "sites")["uses"][0]["geometry_types"] == ["Point"]


def test_contract_is_deterministic_and_digest_covers_report_body():
    workflow = _load(PLAN_WORKFLOW_PATH)
    first = build_workflow_contract(workflow, ["source", "mask", "unused"])
    second = build_workflow_contract(deepcopy(workflow), ["unused", "mask", "source"])
    assert first == second
    body = deepcopy(first)
    digest = body.pop("contract_digest")
    assert digest == digest_json(body)


def test_contract_never_executes_registered_operators(monkeypatch):
    def unexpected_execution(inputs, parameters):
        raise AssertionError((inputs, parameters))

    monkeypatch.setitem(workflow_module.OPERATORS, "geometry_metrics", unexpected_execution)
    report = build_workflow_contract(
        _single_step("geometry_metrics", {"input": "features"}, {}),
        {"features"},
    )
    assert report["layers"][0]["use_count"] == 1


def test_markdown_renderer_matches_tracked_example_and_escapes_labels():
    report = build_workflow_contract(
        _load(PLAN_WORKFLOW_PATH), {"source", "mask", "unused"}
    )
    assert render_workflow_contract_markdown(report) == MARKDOWN_EXAMPLE_PATH.read_text(
        encoding="utf-8"
    )

    layer_name = "sites`\nnext"
    report = build_workflow_contract(
        _single_step(
            "buffer",
            {"input": layer_name},
            {
                "distance": 5,
                "source_crs": "EPSG:4326",
                "work_crs": "EPSG:3857",
            },
        ),
        {layer_name},
    )
    markdown = render_workflow_contract_markdown(report)
    assert "sites\\` next" in markdown
    assert "\nnext" not in markdown

    with pytest.raises(ValidationError, match="schema version 1"):
        render_workflow_contract_markdown({"schema_version": 2})
    with pytest.raises(ValidationError, match="layers array"):
        render_workflow_contract_markdown({"schema_version": 1})


def test_contract_command_prints_and_writes_reports(tmp_path, capsys):
    args = [
        "contract",
        str(PLAN_WORKFLOW_PATH),
        "--layer-name",
        "source",
        "--layer-name",
        "mask",
        "--layer-name",
        "unused",
    ]
    assert main(args + ["--format", "json"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["layer_count"] == 3
    assert captured.err == ""

    output = tmp_path / "contract.md"
    assert main(args + ["--output", str(output)]) == 0
    capsys.readouterr()
    assert output.read_text(encoding="utf-8") == MARKDOWN_EXAMPLE_PATH.read_text(
        encoding="utf-8"
    )


def test_contract_command_rejects_overwrite_and_preserves_diagnostics(tmp_path, capsys):
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(PLAN_WORKFLOW_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    assert (
        main(
            [
                "contract",
                str(workflow_path),
                "--layer-name",
                "source",
                "--layer-name",
                "mask",
                "--output",
                str(workflow_path),
            ]
        )
        == 2
    )
    assert "must not overwrite" in capsys.readouterr().err

    assert (
        main(
            [
                "contract",
                str(workflow_path),
                "--diagnostic-format",
                "json",
            ]
        )
        == 2
    )
    payload = json.loads(capsys.readouterr().err)
    assert payload["error"] == "workflow_validation"
    assert payload["diagnostic"]["code"] == "unknown_input_layer"
