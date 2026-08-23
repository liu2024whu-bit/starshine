from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import Any

import geopandas
from shapely.geometry import Polygon

import starshine_geo

_PACKAGE_NAME = "starshine-geo"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run(command: list[str], *, expected_returncode: int) -> subprocess.CompletedProcess[str]:
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


def _workflow() -> dict[str, Any]:
    return {
        "version": 1,
        "steps": [
            {
                "operation": "reproject",
                "inputs": {"input": "source"},
                "parameters": {"target_crs": "EPSG:3857"},
                "output": "projected",
            },
            {
                "operation": "clip",
                "inputs": {"input": "projected", "mask": "mask"},
                "parameters": {},
                "output": "clipped",
            },
        ],
    }


def _write_package(path: Path) -> None:
    source = geopandas.GeoDataFrame(
        {"feature_id": ["a", "b"]},
        geometry=[
            Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]),
            Polygon([(20, 0), (30, 0), (30, 10), (20, 10), (20, 0)]),
        ],
        crs="EPSG:3857",
    )
    mask = geopandas.GeoDataFrame(
        {"mask_id": ["window"]},
        geometry=[Polygon([(5, -5), (25, -5), (25, 15), (5, 15), (5, -5)])],
        crs="EPSG:3857",
    )
    source.to_file(
        path,
        layer="analysis_source",
        driver="GPKG",
        engine="pyogrio",
        mode="w",
    )
    mask.to_file(
        path,
        layer="analysis_mask",
        driver="GPKG",
        engine="pyogrio",
        mode="a",
    )


def main() -> int:
    installed_version = version(_PACKAGE_NAME)
    if starshine_geo.__version__ != installed_version:
        raise RuntimeError("installed package metadata does not match the public version")
    starshine_command = shutil.which("starshine")
    if starshine_command is None:
        raise RuntimeError("the installed wheel did not provide the starshine console command")

    with tempfile.TemporaryDirectory(prefix="starshine-gpkg-preflight-smoke-") as directory:
        root = Path(directory)
        package = root / "data" / "inputs.gpkg"
        package.parent.mkdir()
        workflow_path = root / "workflow.json"
        json_report_path = root / "reports" / "preflight.json"
        sarif_path = root / "reports" / "preflight.sarif"
        inventory_path = root / "reports" / "inventory.json"
        workflow = _workflow()
        _write_json(workflow_path, workflow)
        _write_package(package)

        direct_inventory = starshine_geo.inventory_geopackage(package)
        if direct_inventory.get("layer_count") != 2:
            raise RuntimeError(f"unexpected GeoPackage inventory layers: {direct_inventory}")
        if direct_inventory.get("bounds_requested") is not False:
            raise RuntimeError("GeoPackage inventory exposed bounds without opt-in")
        inventory_serialized = json.dumps(direct_inventory, sort_keys=True)
        if '"a"' in inventory_serialized or '"window"' in inventory_serialized:
            raise RuntimeError("GeoPackage inventory exposed attribute values")

        inventory_result = _run(
            [
                starshine_command,
                "inventory",
                str(package),
                "--format",
                "json",
                "--output",
                str(inventory_path),
            ],
            expected_returncode=0,
        )
        if inventory_result.stdout.strip() != str(inventory_path) or inventory_result.stderr:
            raise RuntimeError(f"unexpected GeoPackage inventory CLI streams: {inventory_result}")
        cli_inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        if cli_inventory != direct_inventory:
            raise RuntimeError("installed GeoPackage inventory CLI differs from the public API")

        direct_report = starshine_geo.preflight_workflow_inputs(
            workflow,
            {
                "source": starshine_geo.read_geopackage(package, layer="analysis_source"),
                "mask": starshine_geo.read_geopackage(package, layer="analysis_mask"),
            },
        )
        if direct_report.get("valid") is not True:
            raise RuntimeError(f"unexpected direct GeoPackage Preflight report: {direct_report}")

        result = _run(
            [
                starshine_command,
                "preflight",
                str(workflow_path),
                "--geopackage-layer",
                "source",
                str(package),
                "analysis_source",
                "--gpkg-layer",
                "mask",
                str(package),
                "analysis_mask",
                "--format",
                "json",
                "--output",
                str(json_report_path),
            ],
            expected_returncode=0,
        )
        if result.stdout.strip() != str(json_report_path) or result.stderr:
            raise RuntimeError(f"unexpected GeoPackage Preflight CLI streams: {result}")
        cli_report = json.loads(json_report_path.read_text(encoding="utf-8"))
        if cli_report != direct_report:
            raise RuntimeError("installed GeoPackage Preflight CLI differs from the public API")

        sarif_result = _run(
            [
                starshine_command,
                "preflight",
                str(workflow_path),
                "--gpkg-layer",
                "source",
                str(package),
                "analysis_source",
                "--gpkg-layer",
                "mask",
                str(package),
                "analysis_mask",
                "--format",
                "sarif",
                "--sarif-root",
                str(root),
                "--output",
                str(sarif_path),
            ],
            expected_returncode=0,
        )
        if sarif_result.stdout.strip() != str(sarif_path) or sarif_result.stderr:
            raise RuntimeError(f"unexpected GeoPackage SARIF CLI streams: {sarif_result}")
        sarif = json.loads(sarif_path.read_text(encoding="utf-8"))
        results = sarif["runs"][0]["results"]
        if not results:
            raise RuntimeError(f"expected a deferred CRS warning in SARIF: {sarif}")
        artifact_uris = {
            item["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
            for item in results
        }
        if artifact_uris != {"data/inputs.gpkg"}:
            raise RuntimeError(f"unexpected GeoPackage SARIF artifact URIs: {artifact_uris}")

        duplicate_result = _run(
            [
                starshine_command,
                "preflight",
                str(workflow_path),
                "--layer",
                "source=does-not-exist.geojson",
                "--gpkg-layer",
                "source",
                "does-not-exist.gpkg",
                "analysis_source",
            ],
            expected_returncode=2,
        )
        if "duplicate layer name" not in duplicate_result.stderr:
            raise RuntimeError("duplicate logical names were not rejected before source I/O")

        package_digest = hashlib.sha256(package.read_bytes()).hexdigest()
        overwrite_result = _run(
            [
                starshine_command,
                "preflight",
                str(workflow_path),
                "--gpkg-layer",
                "source",
                str(package),
                "analysis_source",
                "--gpkg-layer",
                "mask",
                str(package),
                "analysis_mask",
                "--output",
                str(package),
            ],
            expected_returncode=2,
        )
        if "must not overwrite an input layer" not in overwrite_result.stderr:
            raise RuntimeError("GeoPackage overwrite guard did not produce an actionable error")
        if hashlib.sha256(package.read_bytes()).hexdigest() != package_digest:
            raise RuntimeError("GeoPackage Preflight modified its source artifact")

    print(
        json.dumps(
            {
                "artifact_uri": "data/inputs.gpkg",
                "formats": ["inventory", "json", "sarif"],
                "starshine_version": installed_version,
                "status": "ok",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
