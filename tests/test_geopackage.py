import importlib

import pytest

from starshine_geo.errors import ValidationError
from starshine_geo.geopackage import (
    _require_optional_backend,
    read_geopackage,
    write_geopackage,
)


COLLECTION = {
    "type": "FeatureCollection",
    "starshine:crs": "EPSG:3857",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "site-a"},
            "geometry": {"type": "Point", "coordinates": [1, 1]},
        }
    ],
}


def test_read_requires_explicit_layer_for_multiple_layers(tmp_path, monkeypatch):
    package = tmp_path / "study.gpkg"
    package.touch()
    monkeypatch.setattr(
        "starshine_geo.geopackage._list_layers_backend",
        lambda path: ["zones", "sites"],
    )

    with pytest.raises(ValidationError, match="select one explicitly"):
        read_geopackage(package)


def test_read_preserves_and_validates_crs(tmp_path, monkeypatch):
    package = tmp_path / "study.gpkg"
    package.touch()
    monkeypatch.setattr(
        "starshine_geo.geopackage._list_layers_backend",
        lambda path: ["sites"],
    )
    monkeypatch.setattr(
        "starshine_geo.geopackage._read_layer_backend",
        lambda path, layer: (
            {"type": "FeatureCollection", "features": COLLECTION["features"]},
            "EPSG:3857",
        ),
    )

    result = read_geopackage(package)

    assert result["starshine:crs"] == "EPSG:3857"
    assert result["features"][0]["properties"]["name"] == "site-a"


def test_read_rejects_unknown_layer(tmp_path, monkeypatch):
    package = tmp_path / "study.gpkg"
    package.touch()
    monkeypatch.setattr(
        "starshine_geo.geopackage._list_layers_backend",
        lambda path: ["sites"],
    )

    with pytest.raises(ValidationError, match="available layers"):
        read_geopackage(package, layer="missing")


def test_read_rejects_layer_without_crs(tmp_path, monkeypatch):
    package = tmp_path / "study.gpkg"
    package.touch()
    monkeypatch.setattr(
        "starshine_geo.geopackage._list_layers_backend",
        lambda path: ["sites"],
    )
    monkeypatch.setattr(
        "starshine_geo.geopackage._read_layer_backend",
        lambda path, layer: (
            {"type": "FeatureCollection", "features": COLLECTION["features"]},
            None,
        ),
    )

    with pytest.raises(ValidationError, match="no declared CRS"):
        read_geopackage(package)


def test_write_rejects_existing_destination_without_overwrite(tmp_path, monkeypatch):
    package = tmp_path / "result.gpkg"
    package.touch()
    monkeypatch.setattr(
        "starshine_geo.geopackage._write_layer_backend",
        lambda *args: pytest.fail("backend must not run"),
    )

    with pytest.raises(ValidationError, match="already exists"):
        write_geopackage(COLLECTION, package, layer="results")


def test_write_rejects_input_file_overwrite_without_flag(tmp_path, monkeypatch):
    package = tmp_path / "input.gpkg"
    package.touch()
    monkeypatch.setattr(
        "starshine_geo.geopackage._write_layer_backend",
        lambda *args: pytest.fail("backend must not run"),
    )

    with pytest.raises(ValidationError, match="overwrite an input file"):
        write_geopackage(
            COLLECTION,
            package,
            layer="results",
            input_paths=[package],
        )


def test_write_passes_explicit_layer_and_crs_to_backend(tmp_path, monkeypatch):
    package = tmp_path / "result.gpkg"
    captured = {}

    def fake_write(collection, path, layer, crs):
        captured.update(
            {
                "collection": collection,
                "path": path,
                "layer": layer,
                "crs": crs,
            }
        )

    monkeypatch.setattr("starshine_geo.geopackage._write_layer_backend", fake_write)

    result = write_geopackage(COLLECTION, package, layer="results")

    assert result == package
    assert captured["path"] == package
    assert captured["layer"] == "results"
    assert captured["crs"] == "EPSG:3857"
    assert captured["collection"] == COLLECTION


def test_optional_dependency_error_is_actionable(monkeypatch):
    def missing_dependency(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(importlib, "import_module", missing_dependency)

    with pytest.raises(ValidationError, match="starshine-geo\[geopackage\]"):
        _require_optional_backend()
