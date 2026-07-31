from __future__ import annotations

import json
from pathlib import Path

import pytest

from starshine_geo import preflight_workflow_inputs, read_geopackage
from starshine_geo.cli import main

geopandas = pytest.importorskip("geopandas")
pytest.importorskip("pyogrio")

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "examples" / "plan.workflow.json"
SOURCE_PATH = ROOT / "examples" / "data" / "clip-source.geojson"
MASK_PATH = ROOT / "examples" / "data" / "clip-mask.geojson"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_multilayer_package(path: Path) -> None:
    source = _load(SOURCE_PATH)
    mask = _load(MASK_PATH)
    source_frame = geopandas.GeoDataFrame.from_features(
        source["features"], crs=source["starshine:crs"]
    )
    mask_frame = geopandas.GeoDataFrame.from_features(
        mask["features"], crs=mask["starshine:crs"]
    )
    source_frame.to_file(
        path,
        layer="analysis_source",
        driver="GPKG",
        engine="pyogrio",
        mode="w",
    )
    mask_frame.to_file(
        path,
        layer="analysis_mask",
        driver="GPKG",
        engine="pyogrio",
        mode="a",
    )


def test_real_multilayer_geopackage_preflight_matches_public_api(tmp_path, capsys):
    package = tmp_path / "inputs.gpkg"
    _write_multilayer_package(package)

    result = main(
        [
            "preflight",
            str(WORKFLOW_PATH),
            "--geopackage-layer",
            "source",
            str(package),
            "analysis_source",
            "--gpkg-layer",
            "mask",
            str(package),
            "analysis_mask",
            "--format",
            "json",
        ]
    )

    direct = preflight_workflow_inputs(
        _load(WORKFLOW_PATH),
        {
            "source": read_geopackage(package, layer="analysis_source"),
            "mask": read_geopackage(package, layer="analysis_mask"),
        },
    )
    assert result == 0
    assert json.loads(capsys.readouterr().out) == direct


def test_real_mixed_geojson_and_geopackage_preflight(tmp_path, capsys):
    package = tmp_path / "inputs.gpkg"
    _write_multilayer_package(package)

    result = main(
        [
            "preflight",
            str(WORKFLOW_PATH),
            "--layer",
            f"source={SOURCE_PATH}",
            "--gpkg-layer",
            "mask",
            str(package),
            "analysis_mask",
            "--format",
            "json",
        ]
    )

    assert result == 0
    report = json.loads(capsys.readouterr().out)
    assert report["valid"] is True
    assert report["checked_layer_count"] == 2
    assert {layer["name"] for layer in report["layers"]} == {"source", "mask"}


def test_geopackage_preflight_sarif_uses_container_artifact_uri(tmp_path, capsys):
    package = tmp_path / "data" / "inputs.gpkg"
    package.parent.mkdir()
    _write_multilayer_package(package)
    workflow = tmp_path / "workflow.json"
    workflow.write_text(WORKFLOW_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    output = tmp_path / "reports" / "preflight.sarif"

    result = main(
        [
            "preflight",
            str(workflow),
            "--gpkg-layer",
            "source",
            str(package),
            "analysis_source",
            "--gpkg-layer",
            "mask",
            str(package),
            "analysis_mask",
            "--format",
            "sarif",
            "--sarif-root",
            str(tmp_path),
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert capsys.readouterr().out.strip() == str(output)
    sarif = json.loads(output.read_text(encoding="utf-8"))
    assert sarif["runs"][0]["results"]
    assert {
        item["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        for item in sarif["runs"][0]["results"]
    } == {"data/inputs.gpkg"}
