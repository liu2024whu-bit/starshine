from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import Any

import starshine_geo

_PACKAGE_NAME = "starshine-geo"


def _run(command: list[str], *, expected_returncode: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != expected_returncode:
        raise RuntimeError(
            "command failed\n"
            f"command: {command!r}\n"
            f"expected return code: {expected_returncode}\n"
            f"actual return code: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _assert_installed_location() -> Path:
    package_file = Path(starshine_geo.__file__).resolve()
    current_directory = Path.cwd().resolve()
    if package_file.is_relative_to(current_directory):
        raise RuntimeError(f"Starshine was imported from the working tree: {package_file}")

    workspace_value = os.environ.get("GITHUB_WORKSPACE")
    if workspace_value:
        workspace = Path(workspace_value).resolve()
        if package_file.is_relative_to(workspace):
            raise RuntimeError(f"Starshine was imported from GITHUB_WORKSPACE: {package_file}")
    return package_file


def _assert_public_imports() -> None:
    expected_callables = (
        "buffer_features",
        "build_manifest",
        "digest_json",
        "dissolve_features",
        "inspect_feature_collection",
        "list_geopackage_layers",
        "read_geopackage",
        "run_workflow",
        "summarize_points_within",
        "validate_feature_collection",
        "validate_workflow",
        "write_geopackage",
    )
    missing = [name for name in expected_callables if not callable(getattr(starshine_geo, name, None))]
    if missing:
        raise RuntimeError(f"installed wheel is missing public callables: {missing}")


def _synthetic_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    zones = {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:3857",
        "features": [
            {
                "type": "Feature",
                "properties": {"id": "west"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
                },
            },
            {
                "type": "Feature",
                "properties": {"id": "east"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[10, 0], [20, 0], [20, 10], [10, 10], [10, 0]]],
                },
            },
        ],
    }
    sites = {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:3857",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "site-a"},
                "geometry": {"type": "Point", "coordinates": [2, 2]},
            },
            {
                "type": "Feature",
                "properties": {"name": "site-b"},
                "geometry": {"type": "Point", "coordinates": [8, 8]},
            },
            {
                "type": "Feature",
                "properties": {"name": "site-c"},
                "geometry": {"type": "Point", "coordinates": [15, 5]},
            },
        ],
    }
    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "summarize_points_within",
                "inputs": {"polygons": "zones", "points": "sites"},
                "parameters": {"polygon_id_field": "id", "count_field": "site_count"},
                "output": "summary",
            }
        ],
    }
    return zones, sites, workflow


def _assert_cli_and_demo(starshine_command: str, installed_version: str) -> dict[str, int]:
    zones, sites, workflow = _synthetic_inputs()
    direct_result = starshine_geo.run_workflow(workflow, {"zones": zones, "sites": sites})
    direct_counts = {
        feature["properties"]["id"]: feature["properties"]["site_count"]
        for feature in direct_result["summary"]["features"]
    }
    if direct_counts != {"east": 1, "west": 2}:
        raise RuntimeError(f"unexpected direct API result: {direct_counts}")

    direct_inspection = starshine_geo.inspect_feature_collection(zones)
    if direct_inspection.get("feature_count") != 2:
        raise RuntimeError(f"unexpected direct inspection count: {direct_inspection}")
    if direct_inspection.get("bbox") != [0.0, 0.0, 20.0, 10.0]:
        raise RuntimeError(f"unexpected direct inspection bounds: {direct_inspection}")
    if direct_inspection.get("property_fields") != ["id"]:
        raise RuntimeError(f"unexpected direct inspection fields: {direct_inspection}")

    with tempfile.TemporaryDirectory(prefix="starshine-wheel-smoke-") as directory:
        root = Path(directory)
        workflow_path = root / "workflow.json"
        zones_path = root / "zones.geojson"
        sites_path = root / "sites.geojson"
        output_path = root / "summary.geojson"
        manifest_path = root / "summary.manifest.json"
        inspection_path = root / "zones.inspection.json"
        invalid_path = root / "invalid-workflow.json"

        _write_json(workflow_path, workflow)
        _write_json(zones_path, zones)
        _write_json(sites_path, sites)
        _write_json(
            invalid_path,
            {
                "version": 1,
                "steps": [
                    {
                        "operation": "buffer",
                        "inputs": {"input": "sites"},
                        "parameters": {"distance": 5, "source_crs": "EPSG:3857"},
                        "output": "buffers",
                    }
                ],
            },
        )

        version_result = _run([starshine_command, "--version"])
        if version_result.stdout.strip() != f"starshine {installed_version}":
            raise RuntimeError(f"unexpected version output: {version_result.stdout!r}")

        inspection_result = _run([starshine_command, "inspect", str(zones_path)])
        cli_inspection = json.loads(inspection_result.stdout)
        if cli_inspection != direct_inspection:
            raise RuntimeError(
                f"CLI and direct inspection reports differ: {cli_inspection} != {direct_inspection}"
            )
        _run(
            [
                starshine_command,
                "inspect",
                str(zones_path),
                "--output",
                str(inspection_path),
            ]
        )
        file_inspection = json.loads(inspection_path.read_text(encoding="utf-8"))
        if file_inspection != direct_inspection:
            raise RuntimeError(f"written inspection report differs: {file_inspection}")

        valid_result = _run(
            [
                starshine_command,
                "validate",
                str(workflow_path),
                "--layer-name",
                "zones",
                "--layer-name",
                "sites",
                "--diagnostic-format",
                "json",
            ]
        )
        valid_payload = json.loads(valid_result.stdout)
        if valid_payload != {"valid": True, "workflow_version": 1}:
            raise RuntimeError(f"unexpected validation payload: {valid_payload}")

        invalid_result = _run(
            [
                starshine_command,
                "validate",
                str(invalid_path),
                "--layer-name",
                "sites",
                "--diagnostic-format",
                "json",
            ],
            expected_returncode=2,
        )
        invalid_payload = json.loads(invalid_result.stderr)
        diagnostic = invalid_payload.get("diagnostic", {})
        if diagnostic.get("code") != "missing_parameter" or diagnostic.get("path") != (
            "steps[0].parameters.work_crs"
        ):
            raise RuntimeError(f"unexpected invalid-workflow diagnostic: {invalid_payload}")

        _run(
            [
                starshine_command,
                "run",
                str(workflow_path),
                "--layer",
                f"zones={zones_path}",
                "--layer",
                f"sites={sites_path}",
                "--output-layer",
                "summary",
                "--output",
                str(output_path),
                "--manifest",
                str(manifest_path),
            ]
        )

        output = json.loads(output_path.read_text(encoding="utf-8"))
        cli_counts = {
            feature["properties"]["id"]: feature["properties"]["site_count"]
            for feature in output["features"]
        }
        if cli_counts != direct_counts:
            raise RuntimeError(f"CLI and direct API results differ: {cli_counts} != {direct_counts}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("starshine_version") != installed_version:
            raise RuntimeError(f"manifest has the wrong package version: {manifest}")
        if manifest.get("output_layer", {}).get("name") != "summary":
            raise RuntimeError(f"manifest has the wrong output layer: {manifest}")

    return direct_counts


def main() -> int:
    installed_version = version(_PACKAGE_NAME)
    if starshine_geo.__version__ != installed_version:
        raise RuntimeError(
            "top-level version does not match installed metadata: "
            f"{starshine_geo.__version__!r} != {installed_version!r}"
        )

    package_file = _assert_installed_location()
    _assert_public_imports()
    starshine_command = shutil.which("starshine")
    if starshine_command is None:
        raise RuntimeError("the installed wheel did not provide the starshine console command")

    counts = _assert_cli_and_demo(starshine_command, installed_version)
    print(
        json.dumps(
            {
                "counts": counts,
                "package_file": str(package_file),
                "python": sys.version.split()[0],
                "starshine_command": starshine_command,
                "starshine_version": installed_version,
                "status": "ok",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
