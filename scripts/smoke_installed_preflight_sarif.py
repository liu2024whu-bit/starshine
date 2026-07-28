from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import Any

import starshine_geo

_PACKAGE_NAME = "starshine-geo"


def _write_json(path: Path, value: Any) -> None:
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


def _point(x: float, y: float, **properties: Any) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [x, y]},
    }


def _polygon(**properties: Any) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
        },
    }


def _collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:3857",
        "features": features,
    }


def _workflow(*, output_field: str = "zone_id") -> dict[str, Any]:
    return {
        "version": 1,
        "steps": [
            {
                "operation": "join_points_to_polygons",
                "inputs": {"points": "points", "polygons": "zones"},
                "parameters": {
                    "polygon_id_field": "id",
                    "output_field": output_field,
                },
                "output": "joined",
            }
        ],
    }


def main() -> int:
    installed_version = version(_PACKAGE_NAME)
    if starshine_geo.__version__ != installed_version:
        raise RuntimeError("installed package metadata does not match the public version")
    if not callable(getattr(starshine_geo, "build_workflow_preflight_sarif", None)):
        raise RuntimeError("installed wheel is missing build_workflow_preflight_sarif")
    if starshine_geo.SARIF_VERSION != "2.1.0":
        raise RuntimeError(f"unexpected installed SARIF version: {starshine_geo.SARIF_VERSION}")

    starshine_command = shutil.which("starshine")
    if starshine_command is None:
        raise RuntimeError("the installed wheel did not provide the starshine console command")

    points = _collection([_point(1, 1, point_id="site-a", zone_id="occupied")])
    zones = _collection([_polygon(id="zone-a")])
    workflow = _workflow()
    report = starshine_geo.preflight_workflow_inputs(
        workflow,
        {"points": points, "zones": zones},
    )
    if report.get("valid") is not False:
        raise RuntimeError(f"expected a failing synthetic preflight report: {report}")
    direct_sarif = starshine_geo.build_workflow_preflight_sarif(
        report,
        {"points": "data/points.geojson", "zones": "data/zones.geojson"},
        automation_id="starshine/preflight/workflow.json",
    )
    run = direct_sarif.get("runs", [{}])[0]
    if direct_sarif.get("version") != "2.1.0" or not run.get("results"):
        raise RuntimeError(f"unexpected direct SARIF output: {direct_sarif}")
    if run["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"][
        "uri"
    ] != "data/points.geojson":
        raise RuntimeError(f"unexpected repository-relative SARIF location: {direct_sarif}")

    passing_report = starshine_geo.preflight_workflow_inputs(
        _workflow(output_field="matched_zone"),
        {"points": _collection([_point(1, 1)]), "zones": zones},
    )
    passing_sarif = starshine_geo.build_workflow_preflight_sarif(
        passing_report,
        {"points": "data/points.geojson", "zones": "data/zones.geojson"},
    )
    if passing_sarif["runs"][0]["results"] != []:
        raise RuntimeError(f"passing preflight produced SARIF results: {passing_sarif}")

    with tempfile.TemporaryDirectory(prefix="starshine-sarif-smoke-") as directory:
        root = Path(directory)
        data = root / "data"
        reports = root / "reports"
        data.mkdir()
        workflow_path = root / "workflow.json"
        points_path = data / "points.geojson"
        zones_path = data / "zones.geojson"
        sarif_path = reports / "preflight.sarif"
        _write_json(workflow_path, workflow)
        _write_json(points_path, points)
        _write_json(zones_path, zones)

        result = _run(
            [
                starshine_command,
                "preflight",
                str(workflow_path),
                "--layer",
                f"points={points_path}",
                "--layer",
                f"zones={zones_path}",
                "--format",
                "sarif",
                "--sarif-root",
                str(root),
                "--output",
                str(sarif_path),
            ],
            expected_returncode=1,
        )
        if result.stdout.strip() != str(sarif_path) or result.stderr:
            raise RuntimeError(f"unexpected SARIF CLI streams: {result}")
        cli_sarif = json.loads(sarif_path.read_text(encoding="utf-8"))
        if cli_sarif != direct_sarif:
            raise RuntimeError("installed SARIF CLI output differs from the public API adapter")

    print(
        json.dumps(
            {
                "result_count": len(run["results"]),
                "sarif_version": starshine_geo.SARIF_VERSION,
                "starshine_version": installed_version,
                "status": "ok",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
