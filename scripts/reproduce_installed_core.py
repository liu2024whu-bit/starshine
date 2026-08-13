from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import starshine_geo
from starshine_geo import build_doctor_report, digest_json, run_workflow


def _feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:3857",
        "features": features,
    }


def _polygon(min_x: float, min_y: float, max_x: float, max_y: float, **properties: Any):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [min_x, min_y],
                    [max_x, min_y],
                    [max_x, max_y],
                    [min_x, max_y],
                    [min_x, min_y],
                ]
            ],
        },
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _run(command: list[str], *, expected_codes: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode not in expected_codes:
        raise RuntimeError(
            f"command failed with exit code {result.returncode}: {command[0]} {command[1]}"
        )
    return result


def build_reproduction_report(*, require_geopackage: bool = False) -> dict[str, Any]:
    """Run a self-created end-to-end installed-package reproduction without source fixtures."""
    command = shutil.which("starshine")
    if command is None:
        raise RuntimeError("starshine console command is not available on PATH")

    doctor = build_doctor_report(require_geopackage=require_geopackage)
    if not doctor["valid"]:
        raise RuntimeError("starshine doctor reported an unhealthy runtime")

    left = _feature_collection(
        [
            _polygon(0, 0, 10, 10, parcel="p-1"),
            _polygon(10, 0, 20, 10, parcel="p-2"),
        ]
    )
    right = _feature_collection(
        [
            _polygon(5, -5, 15, 15, zone="z-a"),
            _polygon(20, 0, 30, 10, zone="z-b"),
        ]
    )
    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "intersection",
                "inputs": {"left": "parcels", "right": "zones"},
                "parameters": {"right_id_field": "zone", "output_field": "zone_ref"},
                "output": "overlay",
            }
        ],
    }

    direct = run_workflow(workflow, {"parcels": left, "zones": right})["overlay"]
    expected_pairs = [
        [feature["properties"]["parcel"], feature["properties"]["zone_ref"]]
        for feature in direct["features"]
    ]
    if expected_pairs != [["p-1", "z-a"], ["p-2", "z-a"], ["p-2", "z-b"]]:
        raise RuntimeError("direct public API self-created intersection produced unexpected pairs")

    with tempfile.TemporaryDirectory(prefix="starshine-reproduce-") as directory:
        root = Path(directory)
        workflow_path = root / "workflow.json"
        left_path = root / "parcels.geojson"
        right_path = root / "zones.geojson"
        output_path = root / "overlay.geojson"
        manifest_path = root / "overlay.manifest.json"
        _write_json(workflow_path, workflow)
        _write_json(left_path, left)
        _write_json(right_path, right)

        doctor_cli = _run([command, "doctor", "--format", "json"])
        doctor_from_cli = json.loads(doctor_cli.stdout)
        if not doctor_from_cli["valid"]:
            raise RuntimeError("installed CLI doctor reported an unhealthy runtime")

        _run(
            [
                command,
                "validate",
                str(workflow_path),
                "--layer-name",
                "parcels",
                "--layer-name",
                "zones",
                "--diagnostic-format",
                "json",
            ]
        )
        plan = _run(
            [
                command,
                "plan",
                str(workflow_path),
                "--layer-name",
                "parcels",
                "--layer-name",
                "zones",
            ]
        )
        plan_report = json.loads(plan.stdout)
        if plan_report["terminal_layers"] != ["overlay"]:
            raise RuntimeError("installed CLI plan did not identify the terminal overlay")

        contract = _run(
            [
                command,
                "contract",
                str(workflow_path),
                "--layer-name",
                "parcels",
                "--layer-name",
                "zones",
                "--format",
                "json",
            ]
        )
        contract_report = json.loads(contract.stdout)
        if contract_report["layer_count"] != 2:
            raise RuntimeError("installed CLI contract did not report both external layers")

        preflight = _run(
            [
                command,
                "preflight",
                str(workflow_path),
                "--layer",
                f"parcels={left_path}",
                "--layer",
                f"zones={right_path}",
                "--format",
                "json",
            ]
        )
        preflight_report = json.loads(preflight.stdout)
        if not preflight_report["valid"]:
            raise RuntimeError("installed CLI preflight rejected the self-created inputs")

        _run(
            [
                command,
                "run",
                str(workflow_path),
                "--layer",
                f"parcels={left_path}",
                "--layer",
                f"zones={right_path}",
                "--output-layer",
                "overlay",
                "--output",
                str(output_path),
                "--manifest",
                str(manifest_path),
            ]
        )
        written = json.loads(output_path.read_text(encoding="utf-8"))
        if digest_json(written) != digest_json(direct):
            raise RuntimeError("installed CLI workflow output differs from the public API")

        inspection = _run([command, "inspect", str(output_path)])
        inspection_report = json.loads(inspection.stdout)
        if inspection_report["feature_count"] != 3:
            raise RuntimeError("installed CLI inspection reported the wrong output size")

        quality = _run(
            [command, "quality", str(output_path), "--format", "json"],
            expected_codes=(0, 1),
        )
        quality_report = json.loads(quality.stdout)
        if not quality_report["valid"]:
            raise RuntimeError("self-created overlay failed the installed geometry-quality gate")

        operators = _run([command, "operators"])
        catalog = json.loads(operators.stdout)
        operation_names = [item["name"] for item in catalog["operators"]]
        if "intersection" not in operation_names:
            raise RuntimeError("installed operator catalog is missing intersection")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["starshine_version"] != starshine_geo.__version__:
            raise RuntimeError("installed manifest version differs from package metadata")

    return {
        "schema_version": 1,
        "status": "ok",
        "starshine_version": starshine_geo.__version__,
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "platform": {
            "system": platform.system() or "unknown",
            "machine": platform.machine() or "unknown",
        },
        "doctor_valid": doctor["valid"],
        "geopackage_available": doctor["optional"]["geopackage"]["available"],
        "operator_count": len(operation_names),
        "output_feature_count": len(direct["features"]),
        "output_digest": digest_json(direct),
        "reproduced_steps": [
            "doctor",
            "validate",
            "plan",
            "contract",
            "preflight",
            "run",
            "inspect",
            "quality",
            "operators",
            "manifest",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reproduce the installed Starshine core from self-created data"
    )
    parser.add_argument("--output", type=Path, help="Optionally write the JSON report")
    parser.add_argument(
        "--require-geopackage",
        action="store_true",
        help="Require and exercise the optional GeoPackage backend through starshine doctor",
    )
    args = parser.parse_args(argv)
    report = build_reproduction_report(require_geopackage=args.require_geopackage)
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
