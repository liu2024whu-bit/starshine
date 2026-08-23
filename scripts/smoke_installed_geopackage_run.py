from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import geopandas

from starshine_geo import digest_json, read_geopackage, run_workflow, write_geopackage

CRS = "EPSG:3857"


def _feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "starshine:crs": CRS, "features": features}


def _square(min_x: float, min_y: float, size: float, **properties: object) -> dict:
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [min_x, min_y],
                [min_x + size, min_y],
                [min_x + size, min_y + size],
                [min_x, min_y + size],
                [min_x, min_y],
            ]],
        },
    }


def _write_layer(path: Path, layer: str, collection: dict, *, mode: str) -> None:
    frame = geopandas.GeoDataFrame.from_features(collection["features"], crs=CRS)
    frame.to_file(path, layer=layer, driver="GPKG", engine="pyogrio", mode=mode)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="starshine-gpkg-run-") as raw_tmp:
        root = Path(raw_tmp)
        source = _feature_collection([
            _square(0, 0, 4, source_id="west"),
            _square(4, 0, 4, source_id="east"),
        ])
        mask = _feature_collection([_square(1, -1, 6, mask_id="study")])
        package = root / "inputs.gpkg"
        _write_layer(package, "source", source, mode="w")
        _write_layer(package, "mask", mask, mode="a")

        workflow = {
            "version": 1,
            "steps": [
                {
                    "operation": "clip",
                    "inputs": {"input": "source", "mask": "mask"},
                    "parameters": {},
                    "output": "clipped",
                }
            ],
        }
        workflow_path = root / "workflow.json"
        workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
        output = root / "result.gpkg"
        manifest = root / "manifest.json"

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "starshine_geo.cli",
                "run",
                str(workflow_path),
                "--gpkg-layer",
                "source",
                str(package),
                "source",
                "--gpkg-layer",
                "mask",
                str(package),
                "mask",
                "--output-layer",
                "clipped",
                "--output-format",
                "geopackage",
                "--geopackage-output-layer",
                "clipped_result",
                "--output",
                str(output),
                "--manifest",
                str(manifest),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "installed GeoPackage workflow run failed\n"
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            )

        cli_output = read_geopackage(output, layer="clipped_result")
        expected = run_workflow(
            workflow,
            {
                "source": read_geopackage(package, layer="source"),
                "mask": read_geopackage(package, layer="mask"),
            },
        )["clipped"]
        expected_package = root / "expected.gpkg"
        write_geopackage(expected, expected_package, layer="clipped_result")
        persisted_expected = read_geopackage(expected_package, layer="clipped_result")
        if digest_json(cli_output) != digest_json(persisted_expected):
            raise RuntimeError("installed GeoPackage CLI result differs from persisted public API")
        if not manifest.is_file():
            raise RuntimeError("installed GeoPackage run did not produce a manifest")

    print("Installed-wheel GeoPackage workflow run checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
