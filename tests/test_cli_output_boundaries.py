from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from starshine_geo.cli import main


def _collection(field="field"):
    return {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:3857",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [0, 0]},
            "properties": {field: 1},
        }],
    }


def _cli(*args, encoding="utf-8"):
    return subprocess.run(
        [sys.executable, "-m", "starshine_geo.cli", *map(str, args)],
        capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": encoding},
        check=False,
    )


@pytest.mark.parametrize("format", ["json", "markdown"])
def test_inventory_surrogate_stdout_has_private_safe_error(tmp_path, format):
    source = tmp_path / "source.geojson"
    source.write_text(json.dumps(_collection("private_marker\ud800")), encoding="utf-8")
    result = _cli("inventory", source, "--format", format)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr == b"starshine: Cannot write CLI output to stdout\n"


@pytest.mark.parametrize("command", ["inspect", "inventory"])
def test_ascii_terminal_is_normalized_without_replacing_data(tmp_path, command):
    source = tmp_path / "source.geojson"
    source.write_text(json.dumps(_collection("字段")), encoding="utf-8")
    failed = _cli(command, source, encoding="ascii")
    assert failed.returncode == 2
    assert failed.stdout == b""
    assert failed.stderr == b"starshine: Cannot write CLI output to stdout\n"
    success = _cli(command, source)
    assert success.returncode == 0
    assert "字段" in success.stdout.decode("utf-8")
    assert success.stderr == b""
    output = tmp_path / "report.json"
    saved = _cli(command, source, "--output", output, encoding="ascii")
    assert saved.returncode == 0
    assert "字段" in output.read_text(encoding="utf-8")


@pytest.mark.parametrize("failure_stage", ["write", "flush"])
def test_stdout_write_failure_has_safe_json_diagnostic(
    monkeypatch, capsys, tmp_path, failure_stage,
):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(_collection()), encoding="utf-8")
    class FailedOutput:
        def write(self, text):
            if failure_stage == "write":
                raise OSError("private device detail")

        def flush(self):
            if failure_stage == "flush":
                raise OSError("private device detail")

    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", FailedOutput())
        assert main(["inspect", str(source), "--diagnostic-format", "json"]) == 2
    assert json.loads(capsys.readouterr().err) == {
        "error": "starshine_error",
        "message": "Cannot write CLI output to stdout",
    }


@pytest.mark.parametrize("bad_value", ["private_marker\ud800", float("nan")])
def test_manifest_validation_preserves_both_existing_outputs(tmp_path, bad_value):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(_collection()), encoding="utf-8")
    unused = tmp_path / "unused.json"
    unused.write_text(json.dumps({
        "type": "FeatureCollection", "features": [], "metadata": bad_value,
    }), encoding="utf-8")
    recipe = tmp_path / "workflow.json"
    recipe.write_text(json.dumps({"version": 1, "steps": [{
        "operation": "geometry_metrics", "inputs": {"input": "source"},
        "parameters": {}, "output": "result",
    }]}), encoding="utf-8")
    output = tmp_path / "output.json"
    manifest = tmp_path / "manifest.json"
    output.write_bytes(b"OLD RESULT")
    manifest.write_bytes(b"OLD MANIFEST")
    args = ["run", recipe, "--layer", f"source={source}", "--layer", f"unused={unused}",
            "--output-layer", "result", "--output", output]
    failed = _cli(*args, "--manifest", manifest, "--diagnostic-format", "json")
    assert failed.returncode == 2
    assert failed.stdout == b""
    assert json.loads(failed.stderr)["error"] == "starshine_error"
    assert b"private_marker" not in failed.stderr
    assert b"Traceback" not in failed.stderr
    assert output.read_bytes() == b"OLD RESULT"
    assert manifest.read_bytes() == b"OLD MANIFEST"
    # Optional manifests must not impose a new canonical-JSON policy on ordinary runs.
    success = _cli(*args)
    assert success.returncode == 0
    assert json.loads(output.read_text())["type"] == "FeatureCollection"
    assert manifest.read_bytes() == b"OLD MANIFEST"


def test_manifest_text_encoding_is_checked_before_result_write(tmp_path, capsys):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(_collection()), encoding="utf-8")
    recipe = tmp_path / "workflow.json"
    recipe.write_text(json.dumps({"version": 1, "steps": [{
        "operation": "geometry_metrics", "inputs": {"input": "source"},
        "parameters": {}, "output": "result",
    }]}), encoding="utf-8")
    output = tmp_path / "output.json"
    manifest = tmp_path / "manifest.json"
    output.write_bytes(b"OLD RESULT")
    manifest.write_bytes(b"OLD MANIFEST")
    # An unused logical binding name is copied into the manifest, not hashed as input data.
    # main() also supports programmatic callers that can supply an unencodable alias.
    assert main([
        "run", str(recipe), "--layer", f"source={source}",
        "--layer", f"private_alias\ud800={source}", "--output-layer", "result",
        "--output", str(output), "--manifest", str(manifest),
        "--diagnostic-format", "json",
    ]) == 2
    diagnostic = json.loads(capsys.readouterr().err)
    assert diagnostic["message"] == f"Cannot serialize JSON for {manifest}"
    assert output.read_bytes() == b"OLD RESULT"
    assert manifest.read_bytes() == b"OLD MANIFEST"
