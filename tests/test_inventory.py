from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest
from shapely.geometry import shape as shapely_shape

from starshine_geo import inventory_geojson, render_source_inventory_markdown
from starshine_geo.cli import main as cli_main
from starshine_geo.inventory import inventory_geopackage


def _collection() -> dict:
    return {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:4326",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "private-a", "rank": 1, "active": True},
                "geometry": {"type": "Point", "coordinates": [114.3, 30.5]},
            },
            {
                "type": "Feature",
                "properties": {"name": "private-b", "rank": 2.5, "active": False},
                "geometry": {"type": "Point", "coordinates": [118.8, 32.0]},
            },
        ],
    }


def test_geojson_inventory_omits_values_and_bounds_by_default() -> None:
    report = inventory_geojson(_collection())
    layer = report["layers"][0]

    assert report["source_format"] == "geojson"
    assert report["bounds_requested"] is False
    assert "bounds" not in layer
    assert layer["feature_count_status"] == "known"
    assert layer["feature_count"] == 2
    assert layer["crs_status"] == "declared"
    assert layer["geometry_type"] == "Point"
    assert layer["fields"] == [
        {"name": "active", "types": ["boolean"]},
        {"name": "name", "types": ["string"]},
        {"name": "rank", "types": ["integer", "number"]},
    ]
    serialized = json.dumps(report, sort_keys=True)
    assert "private-a" not in serialized
    assert "private-b" not in serialized


def test_geojson_inventory_bounds_are_explicit_opt_in() -> None:
    report = inventory_geojson(_collection(), include_bounds=True)
    assert report["layers"][0]["bounds"] == [114.3, 30.5, 118.8, 32.0]


def test_geojson_inventory_only_materializes_geometry_for_opt_in_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def counting_shape(value: dict) -> object:
        calls.append(str(value["type"]))
        return shapely_shape(value)

    monkeypatch.setattr("starshine_geo.inventory.shape", counting_shape)

    inventory_geojson(_collection())
    assert calls == []

    report = inventory_geojson(_collection(), include_bounds=True)
    assert calls == ["Point", "Point"]
    assert report["layers"][0]["bounds"] == [114.3, 30.5, 118.8, 32.0]


def test_markdown_does_not_reconstruct_attribute_values() -> None:
    text = render_source_inventory_markdown(inventory_geojson(_collection()))
    assert "`name`: `string`" in text
    assert "private-a" not in text
    assert "114.3" not in text


def test_report_matches_json_schema() -> None:
    schema_path = Path(__file__).parents[1] / "schemas" / "source-inventory-v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(inventory_geojson(_collection()), schema)


def test_inventory_command_writes_json_and_protects_source(tmp_path: Path) -> None:
    source = tmp_path / "source.geojson"
    output = tmp_path / "inventory.json"
    source.write_text(json.dumps(_collection()), encoding="utf-8")

    assert cli_main(["inventory", str(source), "--format", "json", "--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["layer_count"] == 1
    assert cli_main(["inventory", str(source), "--output", str(source)]) == 2


def test_top_level_help_exposes_inventory(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_main(["--help"])
    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "inventory" in output
    assert "GeoJSON or GeoPackage metadata" in output


def test_geopackage_inventory_uses_metadata_without_forcing_expensive_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = tmp_path / "project.gpkg"
    package.write_bytes(b"placeholder")
    calls: list[tuple[str, bool, bool]] = []

    class FakeRows(list):
        def tolist(self) -> list[list[object]]:
            return list(self)

    class FakeArray(list):
        def tolist(self) -> list[object]:
            return list(self)

    fake_pyogrio = SimpleNamespace()
    fake_pyogrio.list_layers = lambda path: FakeRows(
        [["parcels", "Polygon"], ["lookup", None]]
    )

    def read_info(
        path: str,
        *,
        layer: str,
        force_feature_count: bool,
        force_total_bounds: bool,
    ) -> dict:
        calls.append((layer, force_feature_count, force_total_bounds))
        if layer == "lookup":
            return {
                "geometry_type": None,
                "crs": None,
                "fields": FakeArray(["code"]),
                "dtypes": FakeArray(["object"]),
                "features": -1,
                "total_bounds": None,
            }
        return {
            "geometry_type": "Polygon",
            "crs": "EPSG:3857",
            "fields": FakeArray(["parcel_id", "owner"]),
            "dtypes": FakeArray(["int64", "object"]),
            "features": -1,
            "total_bounds": [0.0, 0.0, 10.0, 20.0] if force_total_bounds else None,
        }

    fake_pyogrio.read_info = read_info
    monkeypatch.setattr(
        "starshine_geo.inventory.importlib.import_module",
        lambda name: fake_pyogrio if name == "pyogrio" else __import__(name),
    )

    report = inventory_geopackage(package)
    assert calls == [("parcels", False, False), ("lookup", False, False)]
    assert report["layer_count"] == 2
    assert report["layers"][0]["feature_count"] is None
    assert report["layers"][0]["feature_count_status"] == "unknown"
    assert report["layers"][1]["spatial"] is False
    assert report["layers"][1]["crs_status"] == "not_applicable"
    assert "bounds" not in report["layers"][0]


def test_geopackage_expensive_metadata_is_opt_in(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = tmp_path / "project.gpkg"
    package.write_bytes(b"placeholder")

    fake_pyogrio = SimpleNamespace()
    fake_pyogrio.list_layers = lambda path: [["parcels", "Polygon"]]

    def read_info(
        path: str,
        *,
        layer: str,
        force_feature_count: bool,
        force_total_bounds: bool,
    ) -> dict:
        assert force_feature_count is True
        assert force_total_bounds is True
        return {
            "geometry_type": "Polygon",
            "crs": "EPSG:3857",
            "fields": ["parcel_id"],
            "dtypes": ["int64"],
            "features": 42,
            "total_bounds": [0.0, 0.0, 10.0, 20.0],
        }

    fake_pyogrio.read_info = read_info
    monkeypatch.setattr(
        "starshine_geo.inventory.importlib.import_module",
        lambda name: fake_pyogrio if name == "pyogrio" else __import__(name),
    )

    report = inventory_geopackage(
        package,
        force_feature_count=True,
        include_bounds=True,
    )
    layer = report["layers"][0]
    assert layer["feature_count"] == 42
    assert layer["bounds"] == [0.0, 0.0, 10.0, 20.0]
