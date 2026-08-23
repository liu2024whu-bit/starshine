from __future__ import annotations

import math
import platform
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable

import pyproj
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import Point, box, shape

from ._version import __version__
from .geopackage import list_geopackage_layers, read_geopackage, write_geopackage
from .manifest import digest_json
from .operator_registry import OPERATOR_REGISTRY
from .workflow import run_workflow

DOCTOR_REPORT_VERSION = 1

CheckFunction = Callable[[], str]


def _distribution_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _run_check(name: str, function: CheckFunction) -> dict[str, str]:
    try:
        detail = function()
    except Exception as exc:  # Doctor intentionally keeps checking independent subsystems.
        return {
            "name": name,
            "status": "fail",
            "detail": f"{type(exc).__name__}: self-check failed",
        }
    return {"name": name, "status": "pass", "detail": detail}


def _metadata_check() -> str:
    installed = version("starshine-geo")
    if installed != __version__:
        raise RuntimeError("installed metadata version does not match runtime version")
    return f"installed package metadata matches Starshine {__version__}"


def _proj_check() -> str:
    projected = CRS.from_epsg(3857)
    if projected.to_epsg() != 3857 or not projected.is_projected:
        raise RuntimeError("EPSG:3857 metadata is unavailable")
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x, y = transformer.transform(0.0, 0.0)
    if not math.isfinite(x) or not math.isfinite(y) or abs(x) > 1e-9 or abs(y) > 1e-9:
        raise RuntimeError("PROJ transformation self-check returned an unexpected origin")
    return "CRS database and EPSG:4326 -> EPSG:3857 transformation are available"


def _geos_check() -> str:
    left = box(0.0, 0.0, 2.0, 2.0)
    right = box(1.0, 0.0, 3.0, 2.0)
    result = left.intersection(right)
    if result.is_empty or not math.isclose(result.area, 2.0, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("GEOS intersection self-check returned an unexpected result")
    if not left.covers(Point(0.0, 1.0)):
        raise RuntimeError("GEOS boundary predicate self-check failed")
    return "exact intersection and boundary-inclusive predicates are operational"


def _registry_check() -> str:
    required = {
        "buffer",
        "clip",
        "dissolve",
        "geometry_metrics",
        "intersection",
        "join_points_to_polygons",
        "nearest",
        "reproject",
        "summarize_points_within",
    }
    missing = required.difference(OPERATOR_REGISTRY)
    if missing:
        raise RuntimeError("operator registry is incomplete")
    return f"operator registry exposes {len(OPERATOR_REGISTRY)} reviewed operations"


def _workflow_check() -> str:
    left = {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:3857",
        "features": [
            {
                "type": "Feature",
                "properties": {"parcel": "p-1"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
                    ],
                },
            }
        ],
    }
    right = {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:3857",
        "features": [
            {
                "type": "Feature",
                "properties": {"zone": "z-1"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[5, 0], [15, 0], [15, 10], [5, 10], [5, 0]]
                    ],
                },
            }
        ],
    }
    workflow = {
        "version": 1,
        "steps": [
            {
                "operation": "intersection",
                "inputs": {"left": "left", "right": "right"},
                "parameters": {"right_id_field": "zone", "output_field": "zone_ref"},
                "output": "overlay",
            }
        ],
    }
    output = run_workflow(workflow, {"left": left, "right": right})["overlay"]
    if len(output["features"]) != 1:
        raise RuntimeError("workflow self-check produced an unexpected feature count")
    feature = output["features"][0]
    if feature["properties"] != {"parcel": "p-1", "zone_ref": "z-1"}:
        raise RuntimeError("workflow self-check produced unexpected properties")
    if not math.isclose(shape(feature["geometry"]).area, 50.0, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("workflow self-check produced unexpected geometry")
    return f"registry -> workflow -> indexed overlay path passed ({digest_json(output)})"


def _geopackage_roundtrip_check() -> str:
    collection = {
        "type": "FeatureCollection",
        "starshine:crs": "EPSG:3857",
        "features": [
            {
                "type": "Feature",
                "properties": {"site": "doctor"},
                "geometry": {"type": "Point", "coordinates": [1000.0, 2000.0]},
            }
        ],
    }
    with tempfile.TemporaryDirectory(prefix="starshine-doctor-") as directory:
        package = Path(directory) / "doctor.gpkg"
        write_geopackage(collection, package, layer="sites")
        if list_geopackage_layers(package) != ["sites"]:
            raise RuntimeError("GeoPackage layer listing did not preserve the selected layer")
        restored = read_geopackage(package, layer="sites")
    if restored.get("starshine:crs") != "EPSG:3857":
        raise RuntimeError("GeoPackage round trip did not preserve CRS")
    if restored["features"][0]["properties"] != {"site": "doctor"}:
        raise RuntimeError("GeoPackage round trip did not preserve properties")
    return "temporary GeoPackage write/list/read round trip passed"


def build_doctor_report(*, require_geopackage: bool = False) -> dict[str, Any]:
    """Build a path-free runtime health report without modifying user data."""
    checks = [
        _run_check("package_metadata", _metadata_check),
        _run_check("proj", _proj_check),
        _run_check("geos", _geos_check),
        _run_check("operator_registry", _registry_check),
        _run_check("workflow_execution", _workflow_check),
    ]

    geopandas_version = _distribution_version("geopandas")
    pyogrio_version = _distribution_version("pyogrio")
    geopackage_available = geopandas_version is not None and pyogrio_version is not None
    if geopackage_available:
        geopackage_check = _run_check("geopackage_roundtrip", _geopackage_roundtrip_check)
    elif require_geopackage:
        geopackage_check = {
            "name": "geopackage_roundtrip",
            "status": "fail",
            "detail": 'optional GeoPackage backend is required; install "starshine-geo[geopackage]"',
        }
    else:
        geopackage_check = {
            "name": "geopackage_roundtrip",
            "status": "skip",
            "detail": 'optional GeoPackage backend is not installed; core runtime is unaffected',
        }
    checks.append(geopackage_check)

    valid = all(check["status"] != "fail" for check in checks)
    return {
        "schema_version": DOCTOR_REPORT_VERSION,
        "valid": valid,
        "starshine_version": __version__,
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "platform": {
            "system": platform.system() or "unknown",
            "machine": platform.machine() or "unknown",
        },
        "libraries": {
            "pyproj": {
                "version": pyproj.__version__,
                "proj_version": pyproj.proj_version_str,
            },
            "shapely": {
                "version": shapely.__version__,
                "geos_version": shapely.geos_version_string,
            },
        },
        "optional": {
            "geopackage": {
                "required": require_geopackage,
                "available": geopackage_available,
                "geopandas_version": geopandas_version,
                "pyogrio_version": pyogrio_version,
            }
        },
        "checks": checks,
    }


def render_doctor_text(report: dict[str, Any]) -> str:
    """Render a compact human-readable runtime health report."""
    status = "PASS" if report["valid"] else "FAIL"
    lines = [
        f"Starshine doctor: {status}",
        f"Starshine: {report['starshine_version']}",
        (
            "Python: "
            f"{report['python']['implementation']} {report['python']['version']} "
            f"({report['platform']['system']} {report['platform']['machine']})"
        ),
        (
            "Spatial runtime: "
            f"pyproj {report['libraries']['pyproj']['version']} / "
            f"PROJ {report['libraries']['pyproj']['proj_version']}; "
            f"Shapely {report['libraries']['shapely']['version']} / "
            f"GEOS {report['libraries']['shapely']['geos_version']}"
        ),
        "Checks:",
    ]
    for check in report["checks"]:
        lines.append(f"- {check['status'].upper():4} {check['name']}: {check['detail']}")
    return "\n".join(lines) + "\n"


__all__ = ["DOCTOR_REPORT_VERSION", "build_doctor_report", "render_doctor_text"]
