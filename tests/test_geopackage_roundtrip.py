from copy import deepcopy

import pytest

pytest.importorskip("geopandas")
pytest.importorskip("pyogrio")

from starshine_geo import list_geopackage_layers, read_geopackage, write_geopackage
from starshine_geo.errors import ValidationError


COLLECTION = {
    "type": "FeatureCollection",
    "starshine:crs": "EPSG:3857",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "site-a", "value": 1},
            "geometry": {"type": "Point", "coordinates": [1000, 2000]},
        },
        {
            "type": "Feature",
            "properties": {"name": "site-b", "value": 2},
            "geometry": {"type": "Point", "coordinates": [3000, 4000]},
        },
    ],
}


def test_geopackage_round_trip_preserves_layer_crs_geometry_and_properties(tmp_path):
    package = tmp_path / "sites.gpkg"

    write_geopackage(COLLECTION, package, layer="sites")
    result = read_geopackage(package, layer="sites")

    assert list_geopackage_layers(package) == ["sites"]
    assert result["starshine:crs"] == "EPSG:3857"
    assert [feature["properties"]["name"] for feature in result["features"]] == [
        "site-a",
        "site-b",
    ]
    assert [feature["properties"]["value"] for feature in result["features"]] == [1, 2]
    assert [feature["geometry"]["type"] for feature in result["features"]] == [
        "Point",
        "Point",
    ]
    assert result["features"][0]["geometry"]["coordinates"] == [1000.0, 2000.0]


def test_geopackage_requires_explicit_overwrite_for_existing_output(tmp_path):
    package = tmp_path / "sites.gpkg"
    write_geopackage(COLLECTION, package, layer="sites")

    changed = deepcopy(COLLECTION)
    changed["features"][0]["properties"]["name"] = "site-updated"

    with pytest.raises(ValidationError, match="overwrite=True"):
        write_geopackage(changed, package, layer="sites")

    write_geopackage(changed, package, layer="sites", overwrite=True)
    result = read_geopackage(package, layer="sites")

    assert result["features"][0]["properties"]["name"] == "site-updated"
