import json
from copy import deepcopy
from pathlib import Path

import pytest

from starshine_geo import build_workflow_preflight_sarif, preflight_workflow_inputs
from starshine_geo.cli import main
from starshine_geo.errors import ValidationError

ROOT = Path(__file__).resolve().parents[1]
PLAN_WORKFLOW_PATH = ROOT / "examples" / "plan.workflow.json"
SOURCE_PATH = ROOT / "examples" / "data" / "clip-source.geojson"
MASK_PATH = ROOT / "examples" / "data" / "clip-mask.geojson"
SARIF_EXAMPLE_PATH = ROOT / "examples" / "plan.workflow.preflight.sarif"


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
    return {
        "version": 1,
        "steps": [
            {
                "operation": "join_points_to_polygons",
                "inputs": {"points": "points", "polygons": "zones"},
                "parameters": {"polygon_id_field": "zone_id", **parameters},
                "output": "joined",
            }
        ],
    }


def _failing_report():
    return preflight_workflow_inputs(
        _join_workflow(output_field="zone_id"),
        {
            "points": _collection(
                [
                    _square(0, 0, name="private-value", zone_id="occupied"),
                    _point(1, 1, name="other-private-value", zone_id="occupied"),
                ]
            ),
            "zones": _collection(
                [
                    _square(0, 0, zone_id="duplicate-secret"),
                    _square(20, 0, zone_id="duplicate-secret"),
                    _square(40, 0),
                ]
            ),
        },
    )


def test_sarif_maps_findings_to_rules_results_locations_and_fingerprints():
    report = _failing_report()
    sarif = build_workflow_preflight_sarif(
        report,
        {"points": "examples/data/points.geojson", "zones": "examples/data/zones.geojson"},
        automation_id="starshine/preflight/examples/join.workflow.json",
    )

    assert sarif["$schema"] == "https://json.schemastore.org/sarif-2.1.0.json"
    assert sarif["version"] == "2.1.0"
    run = sarif["runs"][0]
    assert run["automationDetails"]["id"] == (
        "starshine/preflight/examples/join.workflow.json/"
    )
    assert run["invocations"] == [{"executionSuccessful": True}]
    assert len(run["results"]) == len(report["findings"])
    assert [rule["id"] for rule in run["tool"]["driver"]["rules"]] == sorted(
        {f"starshine.preflight.{finding['code']}" for finding in report["findings"]}
    )

    first = run["results"][0]
    assert first["level"] == "error"
    assert first["ruleId"].startswith("starshine.preflight.")
    assert first["locations"][0]["physicalLocation"] == {
        "artifactLocation": {
            "uri": "examples/data/points.geojson",
            "uriBaseId": "%SRCROOT%",
        },
        "region": {"startLine": 1},
    }
    assert first["locations"][0]["logicalLocations"][0]["name"] == "points"
    assert len(first["partialFingerprints"]["starshinePreflight/v1"]) == 64
    assert first["properties"]["occurrenceCount"] >= 1

    serialized = json.dumps(sarif, ensure_ascii=False)
    assert "private-value" not in serialized
    assert "other-private-value" not in serialized
    assert "duplicate-secret" not in serialized


def test_sarif_percent_encodes_repository_paths_without_exposing_absolute_paths():
    report = _failing_report()
    sarif = build_workflow_preflight_sarif(
        report,
        {"points": "data/input points.geojson", "zones": "data/zones.geojson"},
    )
    uris = {
        result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        for result in sarif["runs"][0]["results"]
    }
    assert "data/input%20points.geojson" in uris


def test_sarif_is_deterministic_and_defensive_about_mapping_order():
    report = _failing_report()
    first = build_workflow_preflight_sarif(
        report,
        {"points": "data/points.geojson", "zones": "data/zones.geojson"},
    )
    second = build_workflow_preflight_sarif(
        deepcopy(report),
        {"zones": "data/zones.geojson", "points": "data/points.geojson"},
    )
    assert first == second


def test_passing_preflight_produces_empty_results_and_rules():
    report = preflight_workflow_inputs(
        _join_workflow(),
        {
            "points": _collection([_point(1, 1)]),
            "zones": _collection([_square(0, 0, zone_id="zone-a")]),
        },
    )
    sarif = build_workflow_preflight_sarif(
        report,
        {"points": "points.geojson", "zones": "zones.geojson"},
    )
    run = sarif["runs"][0]
    assert report["valid"] is True
    assert run["results"] == []
    assert run["tool"]["driver"]["rules"] == []
    assert run["properties"]["valid"] is True


@pytest.mark.parametrize(
    "artifact_uris",
    [
        {"points": "/home/user/points.geojson", "zones": "zones.geojson"},
        {"points": "../points.geojson", "zones": "zones.geojson"},
        {"points": "points.geojson"},
    ],
)
def test_sarif_rejects_absolute_parent_or_missing_artifact_uris(artifact_uris):
    with pytest.raises(ValidationError, match="SARIF artifact URI"):
        build_workflow_preflight_sarif(_failing_report(), artifact_uris)


def test_sarif_rejects_malformed_preflight_reports():
    with pytest.raises(ValidationError, match="schema version 1"):
        build_workflow_preflight_sarif({"schema_version": 2}, {})
    with pytest.raises(ValidationError, match="findings array"):
        build_workflow_preflight_sarif({"schema_version": 1, "preflight_digest": "x"}, {})


def test_sarif_example_matches_public_synthetic_preflight():
    report = preflight_workflow_inputs(
        _load(PLAN_WORKFLOW_PATH),
        {"source": _load(SOURCE_PATH), "mask": _load(MASK_PATH)},
    )
    sarif = build_workflow_preflight_sarif(
        report,
        {
            "source": "examples/data/clip-source.geojson",
            "mask": "examples/data/clip-mask.geojson",
        },
        automation_id="starshine/preflight/examples/plan.workflow.json",
    )
    assert sarif == _load(SARIF_EXAMPLE_PATH)
    assert sarif["runs"][0]["results"][0]["level"] == "warning"


def test_preflight_cli_writes_repository_relative_sarif_and_keeps_exit_codes(
    tmp_path,
    capsys,
    monkeypatch,
):
    workflow_path = tmp_path / "join.workflow.json"
    points_path = tmp_path / "data" / "points.geojson"
    zones_path = tmp_path / "data" / "zones.geojson"
    output_path = tmp_path / "reports" / "preflight.sarif"
    points_path.parent.mkdir()
    workflow_path.write_text(json.dumps(_join_workflow(output_field="zone_id")), encoding="utf-8")
    points_path.write_text(
        json.dumps(_collection([_point(1, 1, zone_id="occupied")])), encoding="utf-8"
    )
    zones_path.write_text(
        json.dumps(_collection([_square(0, 0, zone_id="zone-a")])), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    result = main(
        [
            "preflight",
            "join.workflow.json",
            "--layer",
            "points=data/points.geojson",
            "--layer",
            "zones=data/zones.geojson",
            "--format",
            "sarif",
            "--sarif-root",
            ".",
            "--output",
            "reports/preflight.sarif",
        ]
    )
    captured = capsys.readouterr()
    assert result == 1
    assert captured.out.strip() == "reports/preflight.sarif"
    assert captured.err == ""
    sarif = json.loads(output_path.read_text(encoding="utf-8"))
    assert sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
        "artifactLocation"
    ]["uri"] == "data/points.geojson"
    assert sarif["runs"][0]["automationDetails"]["id"] == (
        "starshine/preflight/join.workflow.json/"
    )


def test_preflight_cli_rejects_sarif_paths_outside_root(tmp_path, capsys):
    root = tmp_path / "root"
    root.mkdir()
    workflow_path = root / "workflow.json"
    outside_path = tmp_path / "outside.geojson"
    zones_path = root / "zones.geojson"
    workflow_path.write_text(json.dumps(_join_workflow()), encoding="utf-8")
    outside_path.write_text(json.dumps(_collection([_point(1, 1)])), encoding="utf-8")
    zones_path.write_text(
        json.dumps(_collection([_square(0, 0, zone_id="zone-a")])), encoding="utf-8"
    )

    result = main(
        [
            "preflight",
            str(workflow_path),
            "--layer",
            f"points={outside_path}",
            "--layer",
            f"zones={zones_path}",
            "--format",
            "sarif",
            "--sarif-root",
            str(root),
        ]
    )
    assert result == 2
    assert "contained by --sarif-root" in capsys.readouterr().err


def test_preflight_cli_rejects_sarif_root_for_other_formats(capsys):
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
            "--sarif-root",
            str(ROOT),
        ]
    )
    assert result == 2
    assert "requires --format sarif" in capsys.readouterr().err


def test_sarif_fingerprint_ignores_occurrence_and_sample_details():
    report = _failing_report()
    first = build_workflow_preflight_sarif(
        report,
        {"points": "data/points.geojson", "zones": "data/zones.geojson"},
    )
    changed = deepcopy(report)
    changed_finding = changed["findings"][0]
    changed_finding["occurrence_count"] += 1
    changed_finding["feature_indexes"] = [99]
    second = build_workflow_preflight_sarif(
        changed,
        {"points": "data/points.geojson", "zones": "data/zones.geojson"},
    )
    assert first["runs"][0]["results"][0]["partialFingerprints"] == second["runs"][0][
        "results"
    ][0]["partialFingerprints"]


def test_sarif_treats_percent_characters_as_path_content():
    report = _failing_report()
    sarif = build_workflow_preflight_sarif(
        report,
        {"points": "data/points%20raw.geojson", "zones": "data/zones.geojson"},
    )
    uris = {
        result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        for result in sarif["runs"][0]["results"]
    }
    assert "data/points%2520raw.geojson" in uris


def test_sarif_rejects_invalid_optional_finding_context():
    report = _failing_report()
    report["findings"][0]["step_index"] = True
    with pytest.raises(ValidationError, match="step indexes"):
        build_workflow_preflight_sarif(
            report,
            {"points": "data/points.geojson", "zones": "data/zones.geojson"},
        )


def test_preflight_cli_sarif_keeps_output_overwrite_guards(tmp_path, capsys):
    workflow_path = tmp_path / "workflow.json"
    points_path = tmp_path / "points.geojson"
    zones_path = tmp_path / "zones.geojson"
    workflow_path.write_text(json.dumps(_join_workflow()), encoding="utf-8")
    points_path.write_text(json.dumps(_collection([_point(1, 1)])), encoding="utf-8")
    zones_path.write_text(
        json.dumps(_collection([_square(0, 0, zone_id="zone-a")])), encoding="utf-8"
    )

    result = main(
        [
            "preflight",
            str(workflow_path),
            "--layer",
            f"points={points_path}",
            "--layer",
            f"zones={zones_path}",
            "--format",
            "sarif",
            "--sarif-root",
            str(tmp_path),
            "--output",
            str(points_path),
        ]
    )
    assert result == 2
    assert "must not overwrite an input layer" in capsys.readouterr().err


def test_preflight_cli_requires_existing_sarif_root(capsys, tmp_path):
    base_args = [
        "preflight",
        str(PLAN_WORKFLOW_PATH),
        "--layer",
        f"source={SOURCE_PATH}",
        "--layer",
        f"mask={MASK_PATH}",
        "--format",
        "sarif",
    ]
    assert main(base_args) == 2
    assert "requires --sarif-root" in capsys.readouterr().err

    missing_root = tmp_path / "missing"
    assert main(base_args + ["--sarif-root", str(missing_root)]) == 2
    assert "existing directory" in capsys.readouterr().err
