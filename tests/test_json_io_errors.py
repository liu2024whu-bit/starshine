from __future__ import annotations

import json
import sys

import pytest

from starshine_geo.cli import main
from starshine_geo.errors import ValidationError
from starshine_geo.io import read_json, write_json, write_text


@pytest.mark.parametrize(
    "raw", [b"\xff", b'{"private":', b'{"x":' + b"[" * 10000 + b"0" + b"]" * 10000 + b"}"]
)
def test_read_failure_has_stable_diagnostic(tmp_path, capsys, raw):
    source = tmp_path / "input.json"
    source.write_bytes(raw)
    assert main(["validate", str(source), "--diagnostic-format", "json"]) == 2
    diagnostic = json.loads(capsys.readouterr().err)
    assert diagnostic["error"] == "starshine_error"
    assert diagnostic["message"] == f"Cannot read JSON from {source}"


def test_integer_parser_limit_is_normalized(tmp_path):
    limit = getattr(sys, "get_int_max_str_digits", lambda: 0)()
    if not limit:
        pytest.skip("interpreter does not enforce an integer string limit")
    source = tmp_path / "input.json"
    source.write_text('{"x":' + "1" * (limit + 1) + "}")
    with pytest.raises(ValidationError, match="Cannot read JSON"):
        read_json(source)


@pytest.mark.parametrize("value", [{"x": "\ud800"}, {"x": object()}])
def test_json_representation_failure_preserves_existing_output(tmp_path, value):
    output = tmp_path / "output.json"
    output.write_bytes(b"PRESERVE")
    with pytest.raises(ValidationError):
        write_json(value, output)
    assert output.read_bytes() == b"PRESERVE"


def test_recursive_serialization_preserves_existing_output(tmp_path):
    value = {}
    value["self"] = value
    output = tmp_path / "output.json"
    output.write_bytes(b"PRESERVE")
    with pytest.raises(ValidationError):
        write_json(value, output)
    assert output.read_bytes() == b"PRESERVE"


def test_text_encoding_failure_preserves_existing_output(tmp_path):
    output = tmp_path / "output.md"
    output.write_bytes(b"PRESERVE")
    with pytest.raises(ValidationError):
        write_text("\ud800", output)
    assert output.read_bytes() == b"PRESERVE"


@pytest.mark.parametrize("command", ["operators", "doctor"])
def test_output_parent_file_is_normalized(tmp_path, capsys, command):
    parent = tmp_path / "parent"
    parent.write_text("PRESERVE")
    assert main([command, "--output", str(parent / "out")]) == 2
    assert "Cannot write text" in capsys.readouterr().err
    assert parent.read_text() == "PRESERVE"


def test_output_directory_is_normalized(tmp_path, capsys):
    assert main(["operators", "--output", str(tmp_path)]) == 2
    assert "Cannot write text" in capsys.readouterr().err


def test_run_surrogate_property_preserves_output(tmp_path, capsys):
    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "reproject",
                "inputs": {"input": "source"},
                "parameters": {"source_crs": "EPSG:4326", "target_crs": "EPSG:3857"},
                "output": "result",
            }
        ],
    }
    collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [0, 0]},
                "properties": {"private": "\ud800"},
            }
        ],
    }
    source = tmp_path / "source.json"
    recipe = tmp_path / "workflow.json"
    output = tmp_path / "output.json"
    source.write_text(json.dumps(collection))
    recipe.write_text(json.dumps(workflow))
    output.write_bytes(b"PRESERVE")
    assert (
        main(
            [
                "run",
                str(recipe),
                "--layer",
                f"source={source}",
                "--output-layer",
                "result",
                "--output",
                str(output),
                "--diagnostic-format",
                "json",
            ]
        )
        == 2
    )
    diagnostic = json.loads(capsys.readouterr().err)
    assert diagnostic["error"] == "starshine_error"
    assert "private" not in diagnostic["message"]
    assert output.read_bytes() == b"PRESERVE"


def test_plan_surrogate_layer_preserves_output(tmp_path, capsys):
    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "reproject",
                "inputs": {"input": "source"},
                "parameters": {"target_crs": "EPSG:3857"},
                "output": "private\ud800",
            }
        ],
    }
    recipe = tmp_path / "workflow.json"
    output = tmp_path / "output.json"
    recipe.write_text(json.dumps(workflow))
    output.write_bytes(b"PRESERVE")
    assert (
        main(
            [
                "plan",
                str(recipe),
                "--layer-name",
                "source",
                "--output",
                str(output),
                "--diagnostic-format",
                "json",
            ]
        )
        == 2
    )
    diagnostic = json.loads(capsys.readouterr().err)
    assert diagnostic["error"] == "starshine_error"
    assert "private" not in diagnostic["message"]
    assert output.read_bytes() == b"PRESERVE"


@pytest.mark.parametrize("value", [{"x": float("nan")}, {"x": object()}])
def test_canonical_representation_errors_are_normalized(value):
    from starshine_geo.manifest import canonical_json

    with pytest.raises(ValidationError, match="Cannot serialize canonical JSON"):
        canonical_json(value)


def test_preflight_retains_non_json_collection_finding():
    from starshine_geo import preflight_workflow_inputs

    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "reproject",
                "inputs": {"input": "source"},
                "parameters": {"target_crs": "EPSG:3857"},
                "output": "result",
            }
        ],
    }
    collection = {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:4326",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [0, 0]},
                "properties": {"private": {1, 2}},
            }
        ],
    }
    report = preflight_workflow_inputs(workflow, {"source": collection})
    assert any(finding["code"] == "non_json_feature_collection" for finding in report["findings"])
