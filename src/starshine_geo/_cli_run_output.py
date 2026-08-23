from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .errors import StarshineError
from .geojson import FeatureCollection
from .io import write_json

_OutputKind = Literal["geojson", "geopackage"]


@dataclass(frozen=True, slots=True)
class PreparedRunOutput:
    """Validated CLI output target whose path relationships were checked before feature I/O."""

    path: Path
    kind: _OutputKind
    geopackage_layer: str | None
    overwrite: bool

    def write(self, collection: FeatureCollection, *, input_paths: tuple[Path, ...]) -> Path:
        if self.kind == "geojson":
            write_json(collection, self.path)
            return self.path

        layer = self.geopackage_layer
        if layer is None:
            raise RuntimeError("GeoPackage output is missing its explicit layer name")
        from .geopackage import write_geopackage

        return write_geopackage(
            collection,
            self.path,
            layer=layer,
            overwrite=self.overwrite,
            input_paths=input_paths,
        )


def prepare_run_output(
    path: Path,
    *,
    output_format: str,
    geopackage_layer: str | None,
    overwrite: bool,
    workflow_path: Path,
    input_paths: tuple[Path, ...],
    manifest_path: Path | None,
) -> PreparedRunOutput:
    """Validate output/manifest paths before any workflow input is loaded."""
    output = path.resolve(strict=False)
    workflow = workflow_path.resolve(strict=False)
    inputs = tuple(source.resolve(strict=False) for source in input_paths)

    if output == workflow:
        raise StarshineError("workflow output must not overwrite the workflow file")
    if output in inputs:
        raise StarshineError("workflow output must not overwrite an input file")

    if manifest_path is not None:
        manifest = manifest_path.resolve(strict=False)
        if manifest == workflow:
            raise StarshineError("workflow manifest must not overwrite the workflow file")
        if manifest in inputs:
            raise StarshineError("workflow manifest must not overwrite an input file")
        if manifest == output:
            raise StarshineError("workflow manifest must not overwrite the workflow output")

    if output_format == "geojson":
        if geopackage_layer is not None:
            raise StarshineError("--geopackage-output-layer requires --output-format geopackage")
        if overwrite:
            raise StarshineError("--overwrite-output is valid only with --output-format geopackage")
        return PreparedRunOutput(path, "geojson", None, False)

    if output_format != "geopackage":
        raise StarshineError(f"unsupported workflow output format: {output_format!r}")
    if geopackage_layer is None or not geopackage_layer.strip() or "\x00" in geopackage_layer:
        raise StarshineError(
            "--output-format geopackage requires a non-empty --geopackage-output-layer"
        )
    if path.suffix.casefold() != ".gpkg":
        raise StarshineError("GeoPackage workflow output must use the .gpkg extension")

    return PreparedRunOutput(path, "geopackage", geopackage_layer.strip(), overwrite)


__all__ = ["PreparedRunOutput", "prepare_run_output"]
