from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from shapely.geometry import shape

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


def _intersection_case() -> tuple[dict, dict[str, dict], str, dict]:
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
    return workflow, {"left": left, "right": right}, "intersections", direct


def _difference_case() -> tuple[dict, dict[str, dict], str, dict]:
    source = _collection([
        _polygon(0, 0, 10, 10, parcel_id="partial"),
        _polygon(20, 0, 30, 10, parcel_id="outside"),
    ])
    mask = _collection([_polygon(5, -5, 15, 15, mask_id="erase")])
    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "difference",
                "inputs": {"input": "source", "mask": "mask"},
                "parameters": {},
                "output": "remaining",
            }
        ],
    }
    direct = starshine_geo.difference_features(source, mask)
    if [feature["properties"]["parcel_id"] for feature in direct["features"]] != [
        "partial",
        "outside",
    ]:
        raise RuntimeError(f"unexpected installed difference result: {direct}")
    if [shape(feature["geometry"]).bounds for feature in direct["features"]] != [
        (0.0, 0.0, 5.0, 10.0),
        (20.0, 0.0, 30.0, 10.0),
    ]:
        raise RuntimeError(f"unexpected installed difference geometry: {direct}")

    contract = starshine_geo.build_workflow_contract(workflow, {"source", "mask"})
    mask_layer = next(layer for layer in contract["layers"] if layer["name"] == "mask")
    if mask_layer["uses"][0]["geometry_types"] != ["Polygon", "MultiPolygon"]:
        raise RuntimeError(f"difference contract omitted polygon mask restriction: {contract}")

    preflight = starshine_geo.preflight_workflow_inputs(
        workflow,
        {"source": source, "mask": mask},
    )
    if not preflight.get("valid"):
        raise RuntimeError(f"installed difference preflight failed: {preflight}")
    return workflow, {"source": source, "mask": mask}, "remaining", direct


def _check_workflow_matches_api(
    workflow: dict,
    layers: dict[str, dict],
    output_layer: str,
    direct: dict,
) -> None:
    workflow_result = starshine_geo.run_workflow(workflow, layers)
    if workflow_result[output_layer] != direct:
        raise RuntimeError(f"installed workflow {output_layer} differs from direct public API")


def _run_cli_case(
    command: str,
    root: Path,
    *,
    name: str,
    workflow: dict,
    layers: dict[str, dict],
    output_layer: str,
    direct: dict,
) -> None:
    workflow_path = root / f"{name}.workflow.json"
    output_path = root / f"{name}.result.geojson"
    _write(workflow_path, workflow)

    args = [command, "run", str(workflow_path)]
    for layer_name, collection in layers.items():
        layer_path = root / f"{name}.{layer_name}.geojson"
        _write(layer_path, collection)
        args.extend(["--layer", f"{layer_name}={layer_path}"])
    args.extend(["--output-layer", output_layer, "--output", str(output_path)])

    result = subprocess.run(args, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"installed {name} CLI failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    written = json.loads(output_path.read_text(encoding="utf-8"))
    if starshine_geo.digest_json(written) != starshine_geo.digest_json(direct):
        raise RuntimeError(f"installed {name} CLI differs from public API")


def main() -> int:
    _assert_installed_location()
    for name in ("intersect_features", "difference_features"):
        if not callable(getattr(starshine_geo, name, None)):
            raise TypeError(f"installed wheel is missing {name}")

    intersection = _intersection_case()
    difference = _difference_case()
    _check_workflow_matches_api(*intersection)
    _check_workflow_matches_api(*difference)

    catalog_names = [item["name"] for item in starshine_geo.operator_catalog()["operators"]]
    for operation in ("intersection", "difference"):
        if operation not in catalog_names:
            raise RuntimeError(f"installed operator catalog omitted {operation}: {catalog_names}")

    command = shutil.which("starshine")
    if command is None:
        raise RuntimeError("installed starshine console script was not found")

    with tempfile.TemporaryDirectory(prefix="starshine-overlay-smoke-") as directory:
        root = Path(directory)
        _run_cli_case(
            command,
            root,
            name="intersection",
            workflow=intersection[0],
            layers=intersection[1],
            output_layer=intersection[2],
            direct=intersection[3],
        )
        _run_cli_case(
            command,
            root,
            name="difference",
            workflow=difference[0],
            layers=difference[1],
            output_layer=difference[2],
            direct=difference[3],
        )

    print("Installed-wheel overlay checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
