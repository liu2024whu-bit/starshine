from __future__ import annotations

import importlib
import json
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path
from typing import Any

from .crs import parse_crs
from .errors import ValidationError
from .geojson import FeatureCollection, validate_feature_collection


def _require_optional_backend() -> tuple[Any, Any]:
    try:
        geopandas = importlib.import_module("geopandas")
        pyogrio = importlib.import_module("pyogrio")
    except ImportError as exc:
        raise ValidationError(
            'GeoPackage support requires optional dependencies; install "starshine-geo[geopackage]"'
        ) from exc
    return geopandas, pyogrio


def _validate_package_path(path: str | Path, *, must_exist: bool) -> Path:
    package = Path(path)
    if package.suffix.casefold() != ".gpkg":
        raise ValidationError("GeoPackage paths must use the .gpkg extension")
    if must_exist and not package.is_file():
        raise ValidationError(f"GeoPackage not found: {package}")
    return package


def _validate_layer_name(layer: str) -> str:
    if not isinstance(layer, str) or not layer.strip() or "\x00" in layer:
        raise ValidationError("GeoPackage layer must be a non-empty string")
    return layer.strip()


def _list_layers_backend(path: Path) -> list[str]:
    _, pyogrio = _require_optional_backend()
    rows = pyogrio.list_layers(str(path))
    if hasattr(rows, "tolist"):
        rows = rows.tolist()

    layers: list[str] = []
    for row in rows:
        if isinstance(row, (list, tuple)) and row:
            layers.append(str(row[0]))
        else:
            layers.append(str(row))
    return layers


def list_geopackage_layers(path: str | Path) -> list[str]:
    """List vector layers in a GeoPackage without loading feature rows."""
    package = _validate_package_path(path, must_exist=True)
    layers = _list_layers_backend(package)
    if not layers:
        raise ValidationError("GeoPackage contains no readable vector layers")
    return layers


def _read_layer_backend(path: Path, layer: str) -> tuple[FeatureCollection, str | None]:
    geopandas, _ = _require_optional_backend()
    frame = geopandas.read_file(str(path), layer=layer, engine="pyogrio")
    crs = None if frame.crs is None else frame.crs.to_string()
    try:
        collection = json.loads(frame.to_json(drop_id=True))
    except TypeError:
        collection = json.loads(frame.to_json())
    return collection, crs


def read_geopackage(path: str | Path, *, layer: str | None = None) -> FeatureCollection:
    """Read one GeoPackage layer into Starshine's in-memory GeoJSON contract.

    A package with multiple vector layers always requires an explicit layer name. A single-layer
    package may omit it. The source layer must declare a valid CRS, which is preserved in the
    returned ``starshine:crs`` member.
    """
    package = _validate_package_path(path, must_exist=True)
    layers = list_geopackage_layers(package)

    selected_layer: str
    if layer is None:
        if len(layers) != 1:
            available = ", ".join(sorted(layers))
            raise ValidationError(
                f"GeoPackage contains multiple layers; select one explicitly: {available}"
            )
        selected_layer = layers[0]
    else:
        selected_layer = _validate_layer_name(layer)
        if selected_layer not in layers:
            available = ", ".join(sorted(layers))
            raise ValidationError(
                f"GeoPackage layer not found: {selected_layer!r}; available layers: {available}"
            )

    collection, crs_value = _read_layer_backend(package, selected_layer)
    validated = validate_feature_collection(collection)
    if not isinstance(crs_value, str) or not crs_value.strip():
        raise ValidationError(f"GeoPackage layer {selected_layer!r} has no declared CRS")
    validated["starshine:crs"] = parse_crs(crs_value).to_string()
    return validated


def _write_layer_backend(
    collection: FeatureCollection,
    path: Path,
    layer: str,
    crs: str,
) -> None:
    geopandas, _ = _require_optional_backend()
    frame = geopandas.GeoDataFrame.from_features(collection["features"], crs=crs)
    frame.to_file(
        str(path),
        layer=layer,
        driver="GPKG",
        engine="pyogrio",
        mode="w",
    )


def write_geopackage(
    collection: FeatureCollection,
    path: str | Path,
    *,
    layer: str,
    overwrite: bool = False,
    input_paths: Iterable[str | Path] = (),
) -> Path:
    """Write a FeatureCollection to one GeoPackage layer.

    Existing destinations and input-file destinations are rejected unless ``overwrite=True`` is
    supplied explicitly. The collection must carry a valid ``starshine:crs`` value.
    """
    destination = _validate_package_path(path, must_exist=False)
    selected_layer = _validate_layer_name(layer)
    validated = validate_feature_collection(collection)
    if not validated["features"]:
        raise ValidationError("GeoPackage output requires at least one feature")

    crs_value = validated.get("starshine:crs")
    if not isinstance(crs_value, str) or not crs_value.strip():
        raise ValidationError("GeoPackage output requires a declared starshine:crs value")
    normalized_crs = parse_crs(crs_value).to_string()

    destination_resolved = destination.resolve(strict=False)
    source_paths = {Path(source).resolve(strict=False) for source in input_paths}
    if destination_resolved in source_paths and not overwrite:
        raise ValidationError(
            "GeoPackage output would overwrite an input file; pass overwrite=True explicitly"
        )
    if destination.exists() and not overwrite:
        raise ValidationError(
            "GeoPackage output already exists; pass overwrite=True explicitly"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_layer_backend(deepcopy(validated), destination, selected_layer, normalized_crs)
    return destination
