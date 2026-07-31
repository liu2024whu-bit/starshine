from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .errors import StarshineError
from .geojson import FeatureCollection
from .io import read_json

_SourceKind = Literal["geojson", "geopackage"]


@dataclass(frozen=True, slots=True)
class _LayerSource:
    name: str
    path: Path
    kind: _SourceKind
    package_layer: str | None = None


@dataclass(frozen=True, slots=True)
class PreparedLayerBindings:
    """Validated CLI source bindings that have not performed feature I/O yet."""

    sources: tuple[_LayerSource, ...]

    @property
    def paths(self) -> dict[str, Path]:
        return {source.name: source.path for source in self.sources}

    def load(self) -> dict[str, FeatureCollection]:
        layers: dict[str, FeatureCollection] = {}
        for source in self.sources:
            if source.kind == "geojson":
                collection = _read_geojson_source(source.path)
            else:
                package_layer = source.package_layer
                if package_layer is None:
                    raise RuntimeError("GeoPackage binding is missing its explicit layer")
                collection = _read_geopackage_source(source.path, package_layer)
            layers[source.name] = collection
        return layers


def _normalize_name(value: str) -> str:
    name = value.strip()
    if not name or "\x00" in name:
        raise StarshineError("workflow layer names must be non-empty and contain no NUL bytes")
    return name


def _parse_geojson_source(value: str) -> _LayerSource:
    if "=" not in value:
        raise StarshineError("--layer must use NAME=PATH")
    raw_name, raw_path = value.split("=", 1)
    name = _normalize_name(raw_name)
    if not raw_path:
        raise StarshineError(f"GeoJSON path is empty for workflow layer {name!r}")
    return _LayerSource(name=name, path=Path(raw_path), kind="geojson")


def _parse_geopackage_source(values: Sequence[str]) -> _LayerSource:
    if len(values) != 3:
        raise StarshineError("--geopackage-layer must use NAME PATH LAYER")
    raw_name, raw_path, raw_layer = values
    name = _normalize_name(raw_name)
    package_layer = raw_layer.strip()
    if not raw_path:
        raise StarshineError(f"GeoPackage path is empty for workflow layer {name!r}")
    if not package_layer or "\x00" in package_layer:
        raise StarshineError(
            f"GeoPackage layer selection must be non-empty for workflow layer {name!r}"
        )
    return _LayerSource(
        name=name,
        path=Path(raw_path),
        kind="geopackage",
        package_layer=package_layer,
    )


def prepare_preflight_layer_bindings(
    geojson_values: Sequence[str],
    geopackage_values: Sequence[Sequence[str]],
) -> PreparedLayerBindings:
    """Validate every logical input binding before source files or optional backends are read."""
    sources = [_parse_geojson_source(value) for value in geojson_values]
    sources.extend(_parse_geopackage_source(value) for value in geopackage_values)

    names: set[str] = set()
    for source in sources:
        if source.name in names:
            raise StarshineError(f"invalid or duplicate layer name: {source.name!r}")
        names.add(source.name)
    return PreparedLayerBindings(tuple(sources))


def _read_geojson_source(path: Path) -> FeatureCollection:
    return read_json(path)


def _read_geopackage_source(path: Path, layer: str) -> FeatureCollection:
    # Keep the optional GeoPackage backend lazy for ordinary imports and GeoJSON-only commands.
    from .geopackage import read_geopackage

    return read_geopackage(path, layer=layer)


__all__ = ["PreparedLayerBindings", "prepare_preflight_layer_bindings"]
