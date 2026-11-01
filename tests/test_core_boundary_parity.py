from __future__ import annotations

import json
from copy import deepcopy

import pytest
from pyproj.exceptions import ProjError

from starshine_geo import (
    assess_geometry_quality,
    digest_json,
    preflight_workflow_inputs,
    reproject_features,
    run_workflow,
)
from starshine_geo.cli import main
from starshine_geo.crs import parse_crs
from starshine_geo.errors import ValidationError

LOCAL_CRS = (
    'LOCAL_CS["Synthetic local grid",LOCAL_DATUM["Local datum",0],'
    'UNIT["metre",1],AXIS["X",EAST],AXIS["Y",NORTH]]'
)


def collection(features, crs="EPSG:3857"):
    return {"type": "FeatureCollection", "starshine:crs": crs, "features": features}


def feature(geometry, **properties):
    return {"type": "Feature", "properties": properties, "geometry": geometry}


def point(x, y):
    return {"type": "Point", "coordinates": [x, y]}


def polygon(x):
    return {"type": "Polygon", "coordinates": [
        [[x, 0], [x + 5, 0], [x + 5, 5], [x, 5], [x, 0]],
    ]}


def identifier_case(operation, ids):
    sources = collection([feature(point(i * 10 + 1, 1)) for i in range(len(ids))])
    candidates = collection([
        feature(point(i * 10 + 1, 1) if operation == "nearest" else polygon(i * 10), id=value)
        for i, value in enumerate(ids)
    ])
    roles, parameter, output = {
        "nearest": ({"source": "a", "candidates": "b"}, "candidate_id_field", "nearest_id"),
        "join_points_to_polygons": (
            {"points": "a", "polygons": "b"}, "polygon_id_field", "polygon_id",
        ),
        "intersection": ({"left": "a", "right": "b"}, "right_id_field", "intersection_id"),
    }[operation]
    workflow = {"version": 1, "steps": [{
        "operation": operation, "inputs": roles, "parameters": {parameter: "id"}, "output": "out",
    }]}
    return workflow, {"a": sources, "b": candidates}, output


OPERATIONS = ["nearest", "join_points_to_polygons", "intersection"]


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("ids", [[-0.0, 0.0], [True, 1, 1.0]])
def test_scalar_identifiers_use_preflight_identity_and_preserve_values(operation, ids):
    workflow, layers, output = identifier_case(operation, ids)
    before = deepcopy(layers)
    assert preflight_workflow_inputs(workflow, layers)["valid"]
    result = run_workflow(workflow, layers)["out"]
    actual = [item["properties"][output] for item in result["features"]]
    # JSON comparison distinguishes signed zero and bool/int/float (Python equality does not).
    assert json.dumps(actual) == json.dumps(ids)
    assert layers == before


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("ids", [[-0.0, -0.0], [0.0, 0.0], [True, True], [1, 1], [1.0, 1.0]])
def test_duplicate_scalar_identifiers_agree_with_preflight(operation, ids):
    workflow, layers, _ = identifier_case(operation, ids)
    report = preflight_workflow_inputs(workflow, layers)
    assert not report["valid"]
    assert "duplicate_required_field" in {item["code"] for item in report["findings"]}
    with pytest.raises(ValidationError, match="duplicate .* identifier"):
        run_workflow(workflow, layers)


@pytest.mark.parametrize("operation", OPERATIONS)
def test_signed_zero_identifiers_cli_preflight_and_execution(tmp_path, capsys, operation):
    workflow, layers, output = identifier_case(operation, [-0.0, 0.0])
    path = tmp_path / "workflow.json"
    path.write_text(json.dumps(workflow), encoding="utf-8")
    args = [str(path)]
    for name, data in layers.items():
        source = tmp_path / f"{name}.json"
        source.write_text(json.dumps(data), encoding="utf-8")
        args += ["--layer", f"{name}={source}"]
    assert main(["preflight", *args, "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"]
    destination = tmp_path / "result.json"
    assert main(["run", *args, "--output-layer", "out", "--output", str(destination)]) == 0
    assert not capsys.readouterr().err
    result = json.loads(destination.read_text(encoding="utf-8"))
    assert json.dumps([f["properties"][output] for f in result["features"]]) == "[-0.0, 0.0]"


@pytest.mark.parametrize("ordinate", [10**400, -(10**400)])
@pytest.mark.parametrize("nested", [False, True])
def test_quality_aggregates_unrepresentable_coordinate_without_losing_digest(ordinate, nested):
    geometry = point(ordinate, 0)
    if nested:
        geometry = {"type": "GeometryCollection", "geometries": [geometry]}
    source = collection([feature(geometry), feature(point(1, 2))])
    before = deepcopy(source)
    report = assess_geometry_quality(source)
    assert source == before
    assert report["collection_digest_status"] == "available"
    assert report["collection_digest"] == digest_json(source)
    assert report["invalid_geometry_count"] == 1
    assert report["valid_geometry_count"] == 1
    assert report["error_count"] == 1
    assert report["findings"][0]["code"] == "non_finite_coordinate"
    assert report["findings"][0]["feature_indexes"] == [0]
    assert str(abs(ordinate)) not in json.dumps(report)


@pytest.mark.parametrize("format", ["json", "markdown"])
def test_quality_cli_large_coordinate_produces_report(tmp_path, capsys, format):
    source = tmp_path / "source.json"
    body = json.dumps(collection([feature(point(10**400, 0))]))
    source.write_text(body, encoding="utf-8")
    assert main(["quality", str(source), "--format", format]) == 1
    captured = capsys.readouterr()
    assert not captured.err
    assert "non_finite_coordinate" in captured.out
    assert source.read_text(encoding="utf-8") == body


def reproject_case():
    workflow = {"version": 1, "steps": [{
        "operation": "reproject", "inputs": {"input": "source"},
        "parameters": {"target_crs": "EPSG:4326"}, "output": "out",
    }]}
    return workflow, collection([feature(point(1, 1))], LOCAL_CRS)


def test_unavailable_coordinate_operation_is_validation_error():
    workflow, source = reproject_case()
    before = deepcopy(source)
    assert parse_crs(LOCAL_CRS).is_engineering
    # Preflight checks metadata; it deliberately does not execute transformations.
    assert preflight_workflow_inputs(workflow, {"source": source})["valid"]
    with pytest.raises(ValidationError, match="transformation could not be created") as exc:
        reproject_features(source, target_crs="EPSG:4326")
    assert isinstance(exc.value.__cause__, ProjError)
    assert "Synthetic local grid" not in str(exc.value)
    assert source == before


def test_unavailable_coordinate_operation_cli_preserves_output(tmp_path, capsys):
    workflow, source = reproject_case()
    wp, sp, out = (tmp_path / name for name in ("workflow.json", "source.json", "out.json"))
    wp.write_text(json.dumps(workflow), encoding="utf-8")
    sp.write_text(json.dumps(source), encoding="utf-8")
    out.write_text("preserve-existing-output", encoding="utf-8")
    assert main([
        "run", str(wp), "--layer", f"source={sp}", "--output-layer", "out",
        "--output", str(out), "--diagnostic-format", "json",
    ]) == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert "transformation could not be created" in json.loads(captured.err)["message"]
    assert "Synthetic local grid" not in captured.err
    assert out.read_text(encoding="utf-8") == "preserve-existing-output"


def test_transformer_creation_does_not_hide_unexpected_programming_errors(monkeypatch):
    import starshine_geo.crs as crs_module

    def unexpected(*args, **kwargs):
        raise RuntimeError("synthetic programming error")

    monkeypatch.setattr(crs_module.Transformer, "from_crs", unexpected)
    with pytest.raises(RuntimeError, match="synthetic programming error"):
        crs_module.geometry_transformer("EPSG:4326", "EPSG:3857")
