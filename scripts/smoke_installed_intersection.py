from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import starshine_geo


def _assert_installed_location() -> None:
    package_file = Path(starshine_geo.__file__).resolve()
    cwd = Path.cwd().resolve()
    if package_file.is_relative_to(cwd):
        raise RuntimeError(f"Starshine was imported from the working tree: {package_file}")
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if workspace and package_file.is_relative_to(Path(workspace).resolve()):
        raise RuntimeError(f"Starshine was imported from GITHUB_WORKSPACE: {package_file}")


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "starshine:crs": "EPSG:3857", "features": features}


def _polygon(min_x: float, min_y: float, max_x: float, max_y: float, **properties) -> dict:
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [min_x, min_y],
                [max_x, min_y],
                [max_x, max_y],
                [min_x, max_y],
                [min_x, min_y],
            ]],
        },
    }


def main() -> int:
    _assert_installed_location()
    if not callable(getattr(starshine_geo, "intersect_features", None)):
        raise TypeError("installed wheel is missing intersect_features")

    left = _collection([
        _polygon(0, 0, 10, 10, parcel_id="a"),
        _polygon(10, 0, 20, 10, parcel_id="b"),
    ])
    right = _collection([
        _polygon(5, -2, 15, 12, zone_id="middle"),
        _polygon(20, 0, 30, 10, zone_id="edge"),
    ])
    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "intersection",
                "inputs": {"left": "left", "right": "right"},
                "parameters": {
                    "right_id_field": "zone_id",
                    "output_field": "planning_zone",
                },
                "output": "intersections",
            }
        ],
    }

    direct = starshine_geo.intersect_features(
        left,
        right,
        right_id_field="zone_id",
        output_field="planning_zone",
    )
    if [feature["properties"]["planning_zone"] for feature in direct["features"]] != [
        "middle",
        "middle",
        "edge",
    ]:
        raise RuntimeError(f"unexpected installed intersection result: {direct}")
    if [feature["geometry"]["type"] for feature in direct["features"]] != [
        "Polygon",
        "Polygon",
        "LineString",
    ]:
        raise RuntimeError(f"boundary intersection was not preserved: {direct}")

    workflow_result = starshine_geo.run_workflow(workflow, {"left": left, "right": right})
    if workflow_result["intersections"] != direct:
        raise RuntimeError("installed workflow intersection differs from direct public API")

    contract = starshine_geo.build_workflow_contract(workflow, {"left", "right"})
    if not any(
        write.get("name") == "planning_zone"
        for layer in contract["layers"]
        if layer["name"] == "left"
        for use in layer["uses"]
        for write in use["written_fields"]
    ):
        raise RuntimeError(f"intersection contract omitted output field: {contract}")

    preflight = starshine_geo.preflight_workflow_inputs(
        workflow, {"left": left, "right": right}
    )
    if not preflight.get("valid"):
        raise RuntimeError(f"installed intersection preflight failed: {preflight}")

    catalog_names = [item["name"] for item in starshine_geo.operator_catalog()["operators"]]
    if "intersection" not in catalog_names:
        raise RuntimeError(f"installed operator catalog omitted intersection: {catalog_names}")

    command = shutil.which("starshine")
    if command is None:
        raise RuntimeError("installed starshine console script was not found")

    with tempfile.TemporaryDirectory(prefix="starshine-intersection-smoke-") as directory:
        root = Path(directory)
        workflow_path = root / "workflow.json"
        left_path = root / "left.geojson"
        right_path = root / "right.geojson"
        output_path = root / "result.geojson"
        _write(workflow_path, workflow)
        _write(left_path, left)
        _write(right_path, right)

        result = subprocess.run(
            [
                command,
                "run",
                str(workflow_path),
                "--layer",
                f"left={left_path}",
                "--layer",
                f"right={right_path}",
                "--output-layer",
                "intersections",
                "--output",
                str(output_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "installed intersection CLI failed\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        written = json.loads(output_path.read_text(encoding="utf-8"))
        if starshine_geo.digest_json(written) != starshine_geo.digest_json(direct):
            raise RuntimeError("installed CLI intersection differs from public API")

    print("Installed-wheel intersection checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
