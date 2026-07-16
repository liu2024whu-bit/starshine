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
        "build_workflow_graph",
        "build_manifest",
        "clip_features",
        "calculate_geometry_metrics",
        "digest_json",
        "dissolve_features",
        "join_points_to_polygons",
        "nearest_features",
        "inspect_feature_collection",
        "operator_catalog",
        "plan_workflow",
        "list_geopackage_layers",
        "read_geopackage",
        "render_workflow_mermaid",
        "reproject_features",
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

    direct_catalog = starshine_geo.operator_catalog()
    catalog_names = [item["name"] for item in direct_catalog["operators"]]
    missing_operators = sorted(
        {"clip", "geometry_metrics", "join_points_to_polygons", "nearest", "reproject"}
        - set(catalog_names)
    )
    if missing_operators:
        raise RuntimeError(
            f"installed operator catalog is missing operators {missing_operators}: {catalog_names}"
        )

    direct_plan = starshine_geo.plan_workflow(workflow, {"zones", "sites", "unused"})
    if direct_plan.get("required_external_layers") != ["sites", "zones"]:
        raise RuntimeError(f"unexpected required workflow-plan layers: {direct_plan}")
    if direct_plan.get("unused_external_layers") != ["unused"]:
        raise RuntimeError(f"unexpected unused workflow-plan layers: {direct_plan}")
    if direct_plan.get("terminal_layers") != ["summary"]:
        raise RuntimeError(f"unexpected workflow-plan terminal layers: {direct_plan}")

    direct_graph = starshine_geo.build_workflow_graph(
        workflow, {"zones", "sites", "unused"}
    )
    if direct_graph.get("node_count") != 5 or direct_graph.get("edge_count") != 3:
        raise RuntimeError(f"unexpected workflow graph size: {direct_graph}")
    if direct_graph.get("terminal_layers") != ["summary"]:
        raise RuntimeError(f"unexpected workflow graph terminal layers: {direct_graph}")
    direct_mermaid = starshine_geo.render_workflow_mermaid(direct_graph)
    if "Step 0: summarize_points_within" not in direct_mermaid:
        raise RuntimeError(f"unexpected Mermaid workflow graph: {direct_mermaid}")
    if "polygon_id_field" in direct_mermaid or "site_count" in direct_mermaid:
        raise RuntimeError("Mermaid workflow graph exposed parameter values")

    nearest_candidates = {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:3857",
        "features": [
            {
                "type": "Feature",
                "properties": {"facility_id": "facility-west"},
                "geometry": {"type": "Point", "coordinates": [0, 0]},
            },
            {
                "type": "Feature",
                "properties": {"facility_id": "facility-east"},
                "geometry": {"type": "Point", "coordinates": [20, 0]},
            },
        ],
    }
    direct_nearest = starshine_geo.nearest_features(
        sites,
        nearest_candidates,
        candidate_id_field="facility_id",
        max_distance=10,
    )
    nearest_properties = [feature["properties"] for feature in direct_nearest["features"]]
    if [item["nearest_id"] for item in nearest_properties] != [
        "facility-west",
        None,
        "facility-east",
    ]:
        raise RuntimeError(f"unexpected nearest matches: {direct_nearest}")


    direct_metrics = starshine_geo.calculate_geometry_metrics(
        zones,
        area_field="area_m2",
        length_field="perimeter_m",
    )
    metric_properties = [feature["properties"] for feature in direct_metrics["features"]]
    if [item["area_m2"] for item in metric_properties] != [100.0, 100.0]:
        raise RuntimeError(f"unexpected geometry areas: {direct_metrics}")
    if [item["perimeter_m"] for item in metric_properties] != [40.0, 40.0]:
        raise RuntimeError(f"unexpected geometry lengths: {direct_metrics}")


    direct_joined = starshine_geo.join_points_to_polygons(
        sites,
        zones,
        polygon_id_field="id",
        output_field="zone_id",
    )
    joined_properties = [feature["properties"] for feature in direct_joined["features"]]
    if [item["zone_id"] for item in joined_properties] != ["west", "west", "east"]:
        raise RuntimeError(f"unexpected point-in-polygon join: {direct_joined}")

    direct_reprojected = starshine_geo.reproject_features(sites, target_crs="EPSG:4326")
    if direct_reprojected.get("starshine:crs") != "EPSG:4326":
        raise RuntimeError(f"unexpected reprojected CRS: {direct_reprojected}")
    if len(direct_reprojected.get("features", [])) != 3:
        raise RuntimeError(f"unexpected reprojected feature count: {direct_reprojected}")

    clip_mask = {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:3857",
        "features": [
            {
                "type": "Feature",
                "properties": {"id": "central-mask"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[5, -5], [15, -5], [15, 15], [5, 15], [5, -5]]],
                },
            }
        ],
    }
    direct_clipped = starshine_geo.clip_features(zones, clip_mask)
    if [feature["properties"]["id"] for feature in direct_clipped["features"]] != [
        "west",
        "east",
    ]:
        raise RuntimeError(f"unexpected clipped feature order: {direct_clipped}")
    clipped_bounds = starshine_geo.inspect_feature_collection(direct_clipped).get("bbox")
    if clipped_bounds != [5.0, 0.0, 15.0, 10.0]:
        raise RuntimeError(f"unexpected clipped bounds: {direct_clipped}")

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
        plan_path = root / "workflow.plan.json"
        graph_path = root / "workflow.graph.json"
        mermaid_path = root / "workflow.mmd"
        invalid_path = root / "invalid-workflow.json"
        reproject_workflow_path = root / "reproject-workflow.json"
        reproject_output_path = root / "sites-wgs84.geojson"
        clip_mask_path = root / "clip-mask.geojson"
        clip_workflow_path = root / "clip-workflow.json"
        clip_output_path = root / "clipped-zones.geojson"
        nearest_candidates_path = root / "nearest-candidates.geojson"
        nearest_workflow_path = root / "nearest-workflow.json"
        nearest_output_path = root / "nearest-sites.geojson"
        join_workflow_path = root / "join-workflow.json"
        join_output_path = root / "joined-sites.geojson"
        metrics_workflow_path = root / "metrics-workflow.json"
        metrics_output_path = root / "measured-zones.geojson"

        _write_json(workflow_path, workflow)
        _write_json(zones_path, zones)
        _write_json(sites_path, sites)
        _write_json(clip_mask_path, clip_mask)
        _write_json(nearest_candidates_path, nearest_candidates)
        _write_json(
            nearest_workflow_path,
            {
                "version": 1,
                "steps": [
                    {
                        "operation": "nearest",
                        "inputs": {"source": "sites", "candidates": "facilities"},
                        "parameters": {
                            "candidate_id_field": "facility_id",
                            "max_distance": 10,
                        },
                        "output": "nearest_sites",
                    }
                ],
            },
        )
        _write_json(
            metrics_workflow_path,
            {
                "version": 1,
                "steps": [
                    {
                        "operation": "geometry_metrics",
                        "inputs": {"input": "zones"},
                        "parameters": {
                            "area_field": "area_m2",
                            "length_field": "perimeter_m",
                        },
                        "output": "measured_zones",
                    }
                ],
            },
        )
        _write_json(
            join_workflow_path,
            {
                "version": 1,
                "steps": [
                    {
                        "operation": "join_points_to_polygons",
                        "inputs": {"points": "sites", "polygons": "zones"},
                        "parameters": {
                            "polygon_id_field": "id",
                            "output_field": "zone_id",
                        },
                        "output": "joined_sites",
                    }
                ],
            },
        )
        _write_json(
            clip_workflow_path,
            {
                "version": 1,
                "steps": [
                    {
                        "operation": "clip",
                        "inputs": {"input": "zones", "mask": "mask"},
                        "parameters": {},
                        "output": "clipped",
                    }
                ],
            },
        )
        _write_json(
            reproject_workflow_path,
            {
                "version": 1,
                "steps": [
                    {
                        "operation": "reproject",
                        "inputs": {"input": "sites"},
                        "parameters": {"target_crs": "EPSG:4326"},
                        "output": "sites_wgs84",
                    }
                ],
            },
        )
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

        catalog_result = _run([starshine_command, "operators"])
        if json.loads(catalog_result.stdout) != direct_catalog:
            raise RuntimeError("installed CLI operator catalog differs from the public API catalog")

        plan_result = _run(
            [
                starshine_command,
                "plan",
                str(workflow_path),
                "--layer-name",
                "zones",
                "--layer-name",
                "sites",
                "--layer-name",
                "unused",
            ]
        )
        if json.loads(plan_result.stdout) != direct_plan:
            raise RuntimeError("installed CLI workflow plan differs from the public API plan")
        _run(
            [
                starshine_command,
                "plan",
                str(workflow_path),
                "--layer-name",
                "zones",
                "--layer-name",
                "sites",
                "--layer-name",
                "unused",
                "--output",
                str(plan_path),
            ]
        )
        if json.loads(plan_path.read_text(encoding="utf-8")) != direct_plan:
            raise RuntimeError("written installed-wheel workflow plan differs from direct planning")

        graph_result = _run(
            [
                starshine_command,
                "graph",
                str(workflow_path),
                "--layer-name",
                "zones",
                "--layer-name",
                "sites",
                "--layer-name",
                "unused",
                "--format",
                "json",
            ]
        )
        if json.loads(graph_result.stdout) != direct_graph:
            raise RuntimeError("installed CLI workflow graph differs from the public API graph")
        _run(
            [
                starshine_command,
                "graph",
                str(workflow_path),
                "--layer-name",
                "zones",
                "--layer-name",
                "sites",
                "--layer-name",
                "unused",
                "--format",
                "json",
                "--output",
                str(graph_path),
            ]
        )
        if json.loads(graph_path.read_text(encoding="utf-8")) != direct_graph:
            raise RuntimeError("written installed-wheel workflow graph differs from direct graph")

        mermaid_result = _run(
            [
                starshine_command,
                "graph",
                str(workflow_path),
                "--layer-name",
                "zones",
                "--layer-name",
                "sites",
                "--layer-name",
                "unused",
            ]
        )
        if mermaid_result.stdout != direct_mermaid:
            raise RuntimeError("installed CLI Mermaid graph differs from the public renderer")
        _run(
            [
                starshine_command,
                "graph",
                str(workflow_path),
                "--layer-name",
                "zones",
                "--layer-name",
                "sites",
                "--layer-name",
                "unused",
                "--output",
                str(mermaid_path),
            ]
        )
        if mermaid_path.read_text(encoding="utf-8") != direct_mermaid:
            raise RuntimeError(
                "written installed-wheel Mermaid graph differs from direct rendering"
            )

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
                str(reproject_workflow_path),
                "--layer",
                f"sites={sites_path}",
                "--output-layer",
                "sites_wgs84",
                "--output",
                str(reproject_output_path),
            ]
        )
        cli_reprojected = json.loads(reproject_output_path.read_text(encoding="utf-8"))
        if starshine_geo.digest_json(cli_reprojected) != starshine_geo.digest_json(
            direct_reprojected
        ):
            raise RuntimeError("CLI and direct reprojection results differ")

        _run(
            [
                starshine_command,
                "run",
                str(clip_workflow_path),
                "--layer",
                f"zones={zones_path}",
                "--layer",
                f"mask={clip_mask_path}",
                "--output-layer",
                "clipped",
                "--output",
                str(clip_output_path),
            ]
        )
        cli_clipped = json.loads(clip_output_path.read_text(encoding="utf-8"))
        if starshine_geo.digest_json(cli_clipped) != starshine_geo.digest_json(direct_clipped):
            raise RuntimeError("CLI and direct clip results differ")

        _run(
            [
                starshine_command,
                "run",
                str(nearest_workflow_path),
                "--layer",
                f"sites={sites_path}",
                "--layer",
                f"facilities={nearest_candidates_path}",
                "--output-layer",
                "nearest_sites",
                "--output",
                str(nearest_output_path),
            ]
        )
        cli_nearest = json.loads(nearest_output_path.read_text(encoding="utf-8"))
        if starshine_geo.digest_json(cli_nearest) != starshine_geo.digest_json(direct_nearest):
            raise RuntimeError("CLI and direct nearest results differ")

        _run(
            [
                starshine_command,
                "run",
                str(metrics_workflow_path),
                "--layer",
                f"zones={zones_path}",
                "--output-layer",
                "measured_zones",
                "--output",
                str(metrics_output_path),
            ]
        )
        cli_metrics = json.loads(metrics_output_path.read_text(encoding="utf-8"))
        if starshine_geo.digest_json(cli_metrics) != starshine_geo.digest_json(
            direct_metrics
        ):
            raise RuntimeError("CLI and direct geometry-metric results differ")

        _run(
            [
                starshine_command,
                "run",
                str(join_workflow_path),
                "--layer",
                f"sites={sites_path}",
                "--layer",
                f"zones={zones_path}",
                "--output-layer",
                "joined_sites",
                "--output",
                str(join_output_path),
            ]
        )
        cli_joined = json.loads(join_output_path.read_text(encoding="utf-8"))
        if starshine_geo.digest_json(cli_joined) != starshine_geo.digest_json(direct_joined):
            raise RuntimeError("CLI and direct point-in-polygon join results differ")

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
