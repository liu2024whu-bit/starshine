from __future__ import annotations

import json
from pathlib import Path

import pytest

from starshine_geo import read_geopackage, run_workflow
from starshine_geo._cli_layer_sources import PreparedLayerBindings
from starshine_geo.cli import main

geopandas = pytest.importorskip("geopandas")
pytest.importorskip("pyogrio")

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "examples" / "plan.workflow.json"
SOURCE_PATH = ROOT / "examples" / "data" / "clip-source.geojson"
MASK_PATH = ROOT / "examples" / "data" / "clip-mask.geojson"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_package(path: Path) -> None:
    source = _load(SOURCE_PATH)
    mask = _load(MASK_PATH)
    source_frame = geopandas.GeoDataFrame.from_features(
        source["features"], crs=source["starshine:crs"]
    )
    mask_frame = geopandas.GeoDataFrame.from_features(mask["features"], crs=mask["starshine:crs"])
    source_frame.to_file(path, layer="analysis_source", driver="GPKG", engine="pyogrio", mode="w")
    mask_frame.to_file(path, layer="analysis_mask", driver="GPKG", engine="pyogrio", mode="a")


def test_run_reads_explicit_geopackage_layers_and_writes_geopackage(tmp_path, capsys):
    package = tmp_path / "inputs.gpkg"
    output = tmp_path / "results.gpkg"
    manifest = tmp_path / "manifest.json"
    _write_package(package)

    result = main(
        [
            "run",
            str(WORKFLOW_PATH),
            "--gpkg-layer",
            "source",
            str(package),
            "analysis_source",
            "--geopackage-layer",
            "mask",
            str(package),
            "analysis_mask",
            "--output-layer",
            "coverage",
            "--output-format",
            "geopackage",
            "--geopackage-output-layer",
            "coverage_result",
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ]
    )

    expected = run_workflow(
        _load(WORKFLOW_PATH),
        {
            "source": read_geopackage(package, layer="analysis_source"),
            "mask": read_geopackage(package, layer="analysis_mask"),
        },
    )["coverage"]
    written = read_geopackage(output, layer="coverage_result")

    assert result == 0
    assert capsys.readouterr().out.strip() == str(output)
    assert written["starshine:crs"] == expected["starshine:crs"]
    assert len(written["features"]) == len(expected["features"])
    assert manifest.is_file()
    manifest_payload = _load(manifest)
    assert manifest_payload["output_layer"]["name"] == "coverage"


def test_run_supports_mixed_geojson_and_geopackage_inputs(tmp_path):
    package = tmp_path / "inputs.gpkg"
    output = tmp_path / "coverage.geojson"
    _write_package(package)

    result = main(
        [
            "run",
            str(WORKFLOW_PATH),
            "--layer",
            f"source={SOURCE_PATH}",
            "--gpkg-layer",
            "mask",
            str(package),
            "analysis_mask",
            "--output-layer",
            "coverage",
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert _load(output)["type"] == "FeatureCollection"


def test_run_rejects_output_input_collision_before_feature_io(tmp_path, monkeypatch, capsys):
    package = tmp_path / "inputs.gpkg"
    package.write_bytes(b"not read")
    workflow = tmp_path / "workflow.json"
    workflow.write_text(WORKFLOW_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    loaded = False

    def fail_load(self: PreparedLayerBindings):
        nonlocal loaded
        loaded = True
        raise AssertionError("feature I/O should not run")

    monkeypatch.setattr(PreparedLayerBindings, "load", fail_load)
    result = main(
        [
            "run",
            str(workflow),
            "--gpkg-layer",
            "source",
            str(package),
            "analysis_source",
            "--output-layer",
            "coverage",
            "--output-format",
            "geopackage",
            "--geopackage-output-layer",
            "coverage",
            "--output",
            str(package),
            "--overwrite-output",
        ]
    )

    assert result == 2
    assert loaded is False
    assert "must not overwrite an input file" in capsys.readouterr().err


def test_run_rejects_manifest_collisions_before_feature_io(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source.geojson"
    source.write_text("{}", encoding="utf-8")
    workflow = tmp_path / "workflow.json"
    workflow.write_text(WORKFLOW_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    loaded = False

    def fail_load(self: PreparedLayerBindings):
        nonlocal loaded
        loaded = True
        raise AssertionError("feature I/O should not run")

    monkeypatch.setattr(PreparedLayerBindings, "load", fail_load)
    result = main(
        [
            "run",
            str(workflow),
            "--layer",
            f"source={source}",
            "--output-layer",
            "coverage",
            "--output",
            str(tmp_path / "result.geojson"),
            "--manifest",
            str(source),
        ]
    )

    assert result == 2
    assert loaded is False
    assert "manifest must not overwrite an input file" in capsys.readouterr().err


def test_run_geopackage_output_requires_explicit_layer(tmp_path, capsys):
    result = main(
        [
            "run",
            str(WORKFLOW_PATH),
            "--layer",
            f"source={SOURCE_PATH}",
            "--layer",
            f"mask={MASK_PATH}",
            "--output-layer",
            "coverage",
            "--output-format",
            "geopackage",
            "--output",
            str(tmp_path / "result.gpkg"),
        ]
    )
    assert result == 2
    assert "requires a non-empty --geopackage-output-layer" in capsys.readouterr().err


def test_run_existing_geopackage_requires_explicit_overwrite(tmp_path, capsys):
    destination = tmp_path / "result.gpkg"
    destination.write_bytes(b"existing")
    args = [
        "run",
        str(WORKFLOW_PATH),
        "--layer",
        f"source={SOURCE_PATH}",
        "--layer",
        f"mask={MASK_PATH}",
        "--output-layer",
        "coverage",
        "--output-format",
        "geopackage",
        "--geopackage-output-layer",
        "coverage",
        "--output",
        str(destination),
    ]
    assert main(args) == 2
    assert "already exists" in capsys.readouterr().err


def test_run_existing_geopackage_can_be_replaced_explicitly(tmp_path):
    destination = tmp_path / "result.gpkg"
    destination.write_bytes(b"existing")
    result = main(
        [
            "run",
            str(WORKFLOW_PATH),
            "--layer",
            f"source={SOURCE_PATH}",
            "--layer",
            f"mask={MASK_PATH}",
            "--output-layer",
            "coverage",
            "--output-format",
            "geopackage",
            "--geopackage-output-layer",
            "coverage",
            "--overwrite-output",
            "--output",
            str(destination),
        ]
    )
    assert result == 0
    assert read_geopackage(destination, layer="coverage")["features"]
